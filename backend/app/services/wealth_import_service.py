from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import threading
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.repos.models import (
    PortfolioAsset,
    PortfolioImport,
    PortfolioSnapshot,
    PortfolioTransaction,
    PortfolioValuation,
)
from app.schemas.wealth_portfolio import ImportCommitResult, ImportPreview
from app.services.wealth_workbook import ParsedWorkbook, parse_workbook


class ImportBlocked(ValueError):
    pass


class PreviewNotFound(KeyError):
    pass


@dataclass(frozen=True)
class _PreviewEntry:
    parsed: ParsedWorkbook
    expires_at: datetime


class PreviewStore:
    def __init__(self, ttl: timedelta = timedelta(minutes=30)) -> None:
        self.ttl = ttl
        self._entries: dict[str, _PreviewEntry] = {}
        self._lock = threading.Lock()

    def put(self, parsed: ParsedWorkbook) -> str:
        token = uuid4().hex
        entry = _PreviewEntry(parsed, datetime.now(timezone.utc) + self.ttl)
        with self._lock:
            self._entries[token] = entry
        return token

    def pop_valid(self, token: str) -> ParsedWorkbook:
        with self._lock:
            entry = self._entries.pop(token, None)
        if entry is None or entry.expires_at <= datetime.now(timezone.utc):
            raise PreviewNotFound(token)
        return entry.parsed


def _snapshot_date(parsed: ParsedWorkbook) -> date:
    effective_dates = [item.occurred_on for item in parsed.transactions]
    effective_dates.extend(item.valued_on for item in parsed.valuations)
    return max(effective_dates, default=date.today())


def _insert_import_and_snapshot(session: Session, parsed: ParsedWorkbook) -> tuple[PortfolioImport, PortfolioSnapshot]:
    import_row = PortfolioImport(
        id=str(uuid4()),
        source_sha256=parsed.source_sha256,
        filename=parsed.filename,
        status="SUCCEEDED",
        issue_counts={
            "warnings": sum(issue.severity == "warning" for issue in parsed.issues),
            "errors": sum(issue.severity == "error" for issue in parsed.issues),
        },
    )
    snapshot = PortfolioSnapshot(
        id=str(uuid4()),
        import_id=import_row.id,
        as_of=_snapshot_date(parsed),
    )
    session.add_all([import_row, snapshot])
    return import_row, snapshot


def _insert_assets(session: Session, snapshot_id: str, parsed: ParsedWorkbook) -> dict[str, str]:
    asset_ids: dict[str, str] = {}
    for item in parsed.assets:
        row_id = str(uuid4())
        asset_ids[item.source_key] = row_id
        session.add(PortfolioAsset(
            id=row_id,
            snapshot_id=snapshot_id,
            source_key=item.source_key,
            asset_type=item.asset_type,
            name=item.name,
            market=item.market,
            currency=item.currency,
            invested_amount=item.invested_amount,
            market_value=item.market_value,
            source_ref=item.source_ref,
        ))
    return asset_ids


def _insert_transactions(
    session: Session,
    snapshot_id: str,
    parsed: ParsedWorkbook,
    asset_ids: dict[str, str],
) -> None:
    for item in parsed.transactions:
        session.add(PortfolioTransaction(
            id=str(uuid4()),
            snapshot_id=snapshot_id,
            source_key=item.source_key,
            asset_id=asset_ids[item.asset_source_key],
            occurred_on=item.occurred_on,
            kind=item.kind,
            amount=item.amount,
            units=item.units,
            unit_price=item.unit_price,
            currency=item.currency,
            source_ref=item.source_ref,
        ))


def _insert_valuations(
    session: Session,
    snapshot_id: str,
    parsed: ParsedWorkbook,
    asset_ids: dict[str, str],
) -> None:
    for item in parsed.valuations:
        session.add(PortfolioValuation(
            id=str(uuid4()),
            snapshot_id=snapshot_id,
            source_key=item.source_key,
            asset_id=asset_ids[item.asset_source_key],
            valued_on=item.valued_on,
            market_value=item.market_value,
            currency=item.currency,
            source_ref=item.source_ref,
        ))


class WealthImportService:
    def __init__(self, store: PreviewStore | None = None) -> None:
        self.store = store or PreviewStore()

    def preview(self, payload: bytes, filename: str) -> ImportPreview:
        parsed = parse_workbook(payload, filename)
        token = self.store.put(parsed)
        return ImportPreview(
            preview_token=token,
            source_sha256=parsed.source_sha256,
            recognized_sheets=parsed.recognized_sheets,
            ignored_sheets=parsed.ignored_sheets,
            counts=parsed.counts,
            issues=parsed.issues,
        )

    def commit(self, session: Session, token: str) -> ImportCommitResult:
        parsed = self.store.pop_valid(token)
        if any(issue.severity == "error" for issue in parsed.issues):
            raise ImportBlocked("preview contains blocking errors")
        with session.begin():
            existing = session.scalar(
                select(PortfolioImport).where(PortfolioImport.source_sha256 == parsed.source_sha256)
            )
            if existing:
                snapshot = session.scalar(
                    select(PortfolioSnapshot).where(PortfolioSnapshot.import_id == existing.id)
                )
                if snapshot is None:
                    raise RuntimeError("portfolio import exists without snapshot")
                return ImportCommitResult(snapshot_id=snapshot.id, created=False)
            _, snapshot = _insert_import_and_snapshot(session, parsed)
            snapshot_id = snapshot.id
            asset_ids = _insert_assets(session, snapshot.id, parsed)
            _insert_transactions(session, snapshot.id, parsed, asset_ids)
            _insert_valuations(session, snapshot.id, parsed, asset_ids)
        return ImportCommitResult(snapshot_id=snapshot_id, created=True)


import_service = WealthImportService()
