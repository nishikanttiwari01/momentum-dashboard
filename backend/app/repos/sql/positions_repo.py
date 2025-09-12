from __future__ import annotations
from datetime import datetime
from sqlalchemy.orm import Session

from ..models import Position
from ..interfaces.base import IPositionsRepo


class SqlPositionsRepo(IPositionsRepo):
    def __init__(self, session: Session):
        self.s = session

    def list_positions(self) -> list[dict]:
        rows = self.s.query(Position).order_by(Position.symbol.asc()).all()
        return [
            {
                "id": r.id,
                "symbol": r.symbol,
                "entry_price_locked": r.entry_price_locked,
                "qty": r.qty,
                "stop_now": r.stop_now,
                "exit_close_threshold": r.exit_close_threshold,
                "breakeven_active": r.breakeven_active,
                "euphoria_on": r.euphoria_on,
                "note": r.note,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rows
        ]

    def lock_entry(self, symbol: str, price: float, qty: int | None) -> None:
        assert price > 0, "entry price must be > 0"
        symbol = symbol.upper()
        now = datetime.utcnow()
        row = self.s.query(Position).filter(Position.symbol == symbol).one_or_none()
        if row:
            # Entry remains immutable once set (we allow fixing None->price once)
            if row.entry_price_locked is None:
                row.entry_price_locked = float(price)
            row.qty = qty
            row.updated_at = now
        else:
            self.s.add(
                Position(
                    symbol=symbol,
                    entry_price_locked=float(price),
                    qty=qty,
                    stop_now=None,
                    exit_close_threshold=None,
                    breakeven_active=False,
                    euphoria_on=False,
                    note=None,
                )
            )
        self.s.flush()  # make visible to immediate reads (tests)

    def update_stop(self, symbol: str, stop_now: float) -> None:
        symbol = symbol.upper()
        row = self.s.query(Position).filter(Position.symbol == symbol).one_or_none()
        if row is None:
            # Do NOT create a dummy position here; invariant tests expect it to pre-exist
            return
        # Trailing behavior: never lower the stop
        if row.stop_now is None or float(stop_now) > float(row.stop_now):
            row.stop_now = float(stop_now)
            row.updated_at = datetime.utcnow()
        self.s.flush()  # ensure visibility in same session/test

    def close_position(self, symbol: str, reason: str) -> None:
        symbol = symbol.upper()
        row = self.s.query(Position).filter(Position.symbol == symbol).one_or_none()
        if row:
            self.s.delete(row)
            self.s.flush()
