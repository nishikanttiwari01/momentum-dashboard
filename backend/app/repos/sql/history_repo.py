from __future__ import annotations
from datetime import datetime, date
from sqlalchemy.orm import Session
from sqlalchemy import select

from ..models import History
from ..interfaces.base import IHistoryRepo


class SqlHistoryRepo(IHistoryRepo):
    def __init__(self, session: Session):
        self.s = session

    def list_history(self, date: datetime | None = None) -> list[dict]:
        q = select(
            History.id,
            History.symbol,
            History.as_of,
            History.outcome,
            History.pnl_pct,
            History.run_id,
            History.meta_json,
        ).order_by(History.as_of.desc(), History.symbol.asc())

        if date is not None:
            day_start = datetime(date.year, date.month, date.day)
            day_end = day_start.replace(hour=23, minute=59, second=59, microsecond=999999)
            q = q.where(History.as_of >= day_start, History.as_of <= day_end)

        rows = self.s.execute(q).all()
        out: list[dict] = []
        for r in rows:
            as_of = r.as_of
            out.append(
                {
                    "id": r.id,
                    "symbol": r.symbol,
                    "as_of": as_of.isoformat() if isinstance(as_of, (datetime, date)) else as_of,
                    "outcome": r.outcome,
                    "pnl_pct": r.pnl_pct,
                    "run_id": r.run_id,
                    "meta_json": r.meta_json,
                }
            )
        return out
