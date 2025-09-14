from __future__ import annotations
from datetime import datetime, date as _date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import History
from ..interfaces.base import IHistoryRepo


class SqlHistoryRepo(IHistoryRepo):
    def __init__(self, session: Session):
        self.s = session

    # Phase 9: minimal stub so services can record summaries without breaking.
    # We'll implement real writes (per-symbol outcomes) in the next phase.
    def insert_run_summary(self, *, run_id: str, as_of: datetime, rows: int) -> None:
        """
        No-op placeholder for Phase 9.
        A future phase will persist aggregated results into a summary/history table.
        """
        return

    def list_history(self, date: Optional[datetime] = None) -> list[dict]:
        """
        Returns history rows, newest day first, symbol ascending within the day.
        If 'date' is provided, constrain to that calendar day (00:00:00 → 23:59:59.999999).
        Accepts either datetime or date (keeps public signature unchanged).
        """
        q = (
            select(
                History.id,
                History.symbol,
                History.as_of,
                History.outcome,
                History.pnl_pct,
                History.run_id,
                History.meta_json,
            )
            .order_by(History.as_of.desc(), History.symbol.asc())
        )

        if date is not None:
            # Support both datetime and date inputs
            if isinstance(date, _date) and not isinstance(date, datetime):
                day_start = datetime(date.year, date.month, date.day, 0, 0, 0, 0)
            else:
                day_start = datetime(date.year, date.month, date.day, 0, 0, 0, 0)
            day_end = day_start.replace(hour=23, minute=59, second=59, microsecond=999_999)
            q = q.where(History.as_of >= day_start, History.as_of <= day_end)

        rows = self.s.execute(q).all()
        out: list[dict] = []
        for r in rows:
            as_of_val = r.as_of
            out.append(
                {
                    "id": r.id,
                    "symbol": r.symbol,
                    "as_of": as_of_val.isoformat() if isinstance(as_of_val, datetime) else str(as_of_val),
                    "outcome": r.outcome,
                    "pnl_pct": r.pnl_pct,
                    "run_id": r.run_id,
                    "meta_json": r.meta_json,
                }
            )
        return out
