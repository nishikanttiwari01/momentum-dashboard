from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date

from app.core import config as app_config
from app.repos.sql.candidate_pool_repo import CandidatePoolRepo
from app.services.candidate_pool_service import CandidatePoolService

# Generated models (contract-first)
from app.schemas.generated.models import CandidatePoolList  # type: ignore

try:
    from app.core.db import get_session  # must yield a Session
except Exception as e:
    get_session = None

router = APIRouter(prefix="/candidate-pool", tags=["Screener"])


def _require_session():
    if get_session is None:
        raise HTTPException(status_code=503, detail="DB not initialized")
    return get_session


@router.get("", response_model=CandidatePoolList)
def list_candidate_pool(s: Session = Depends(_require_session())):
    cfg = app_config.load()
    repo = CandidatePoolRepo(session=s)
    service = CandidatePoolService(repo=repo, cfg=cfg.candidate_pool, strategy=cfg.strategy)

    now = datetime.now(timezone.utc)
    trading_day = now.date()
    rows = repo.list_entries(active_only=True)

    entries = []
    for row in rows:
        entry = service._entry_from_repo(row, now)  # type: ignore[attr-defined]
        checks, notes = service._exit_checks(entry, trading_day)  # type: ignore[attr-defined]
        entry.exit_checks = checks
        entry.reasons = notes
        entry.stale = False
        entries.append(entry)

    ranked = service._rank_entries(entries)  # type: ignore[attr-defined]
    ranked.sort(
        key=lambda e: (
            e.rank_ord if e.rank_ord is not None else 1_000_000,
            -(e.rank_score or 0.0),
            e.symbol,
        )
    )

    items: List[dict] = []
    for idx, entry in enumerate(ranked, start=1):
        entry.rank_ord = entry.rank_ord or idx
        items.append(service.serialize_entry(entry, is_top=idx == 1))

    as_of = next(
        (r.get("last_seen_as_of") or r.get("added_as_of") for r in rows if r.get("last_seen_as_of") or r.get("added_as_of")),
        None,
    )

    return CandidatePoolList(
        max_size=cfg.candidate_pool.max_size,
        run_id=None,
        as_of=as_of,
        generated_at=now.isoformat(),
        items=items,
    )


@router.get("/history", response_model=CandidatePoolList)
def list_candidate_pool_history(date: date, s: Session = Depends(_require_session())):
    cfg = app_config.load()
    repo = CandidatePoolRepo(session=s)
    service = CandidatePoolService(repo=repo, cfg=cfg.candidate_pool, strategy=cfg.strategy)

    rows = repo.list_history(date)
    if not rows:
        return CandidatePoolList(max_size=cfg.candidate_pool.max_size, run_id=None, as_of=date.isoformat(), generated_at=None, items=[])

    items = []
    now = datetime.now(timezone.utc)
    for row in rows:
        # align keys for serializer
        payload = {
            "symbol": row.get("symbol"),
            "rank_ord": row.get("rank_ord"),
            "rank_score": row.get("rank_score"),
            "score": row.get("score"),
            "adx14": row.get("adx14"),
            "atr_pct": row.get("atr_pct"),
            "prox52w": row.get("prox_52w_high_pct"),
            "liquidity": row.get("liquidity"),
            "status": row.get("status") or "ACTIVE",
            "exit_reason": row.get("exit_reason"),
            "added_on": row.get("added_on"),
            "added_as_of": row.get("as_of"),
            "last_seen_as_of": row.get("as_of"),
            "last_price": row.get("last_price"),
            "reasons": [],
            "exit_checks": [],
        }
        try:
            entry = service._entry_from_repo(payload, now)  # type: ignore[attr-defined]
            items.append(service.serialize_entry(entry, is_top=False))
        except Exception:
            continue

    items.sort(key=lambda e: (e.get("rank") if e.get("rank") is not None else 1_000_000, e.get("symbol")))

    return CandidatePoolList(
        max_size=cfg.candidate_pool.max_size,
        run_id=None,
        as_of=date.isoformat(),
        generated_at=None,
        items=items,
    )
