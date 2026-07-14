from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.repos.models import PortfolioFxRate


FRANKFURTER_URL = "https://api.frankfurter.app"


class FxUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class FxResult:
    rate: float
    effective_on: date
    source: str
    fetched_at: datetime
    is_fallback: bool


def _latest_cached(session: Session, requested_on: date) -> PortfolioFxRate | None:
    return session.scalar(
        select(PortfolioFxRate)
        .where(
            PortfolioFxRate.base_currency == "USD",
            PortfolioFxRate.quote_currency == "INR",
            PortfolioFxRate.effective_on <= requested_on,
        )
        .order_by(PortfolioFxRate.effective_on.desc())
        .limit(1)
    )


def _result(row: PortfolioFxRate, *, fallback: bool) -> FxResult:
    return FxResult(
        rate=row.rate,
        effective_on=row.effective_on,
        source=row.source,
        fetched_at=row.fetched_at,
        is_fallback=fallback,
    )


def get_usd_inr(session: Session, requested_on: date, client: Any | None = None) -> FxResult:
    cached = _latest_cached(session, requested_on)
    if cached is not None and cached.effective_on == requested_on:
        return _result(cached, fallback=False)

    http_client = client or httpx
    endpoint = f"{FRANKFURTER_URL}/{requested_on.isoformat()}"
    try:
        response = http_client.get(endpoint, params={"from": "USD", "to": "INR"}, timeout=10)
        response.raise_for_status()
        payload = response.json()
        effective_on = date.fromisoformat(payload["date"])
        rate = float(payload["rates"]["INR"])
        fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)
        row = PortfolioFxRate(
            base_currency="USD",
            quote_currency="INR",
            effective_on=effective_on,
            rate=rate,
            source="frankfurter",
            fetched_at=fetched_at,
        )
        session.add(row)
        session.commit()
        return _result(row, fallback=False)
    except Exception as exc:
        session.rollback()
        cached = _latest_cached(session, requested_on)
        if cached is None:
            raise FxUnavailable(f"USD/INR unavailable for {requested_on.isoformat()}") from exc
        return _result(cached, fallback=True)
