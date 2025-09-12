from __future__ import annotations
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from ..models import Position
from ..interfaces.base import IPositionsRepo


class PositionsRepo(IPositionsRepo):
    def __init__(self, session: Session | None = None):   # <-- allow None
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
                # Note: list API does not expose entry_price / trade_on
            }
            for r in rows
        ]

    # Phase 8: minimal addition
    def get(self, symbol: str) -> Optional[Dict[str, Any]]:
        # Safe when no DB wired (used by stub/route-json tests)
        if self.s is None:
            return None
        row = (
            self.s.query(Position)
            .filter(Position.symbol == symbol.upper())
            .one_or_none()
        )
        if row is None:
            return None
        qty = row.qty
        return {
            "id": row.id,
            "symbol": row.symbol,
            "entry_price": None,
            "entry_price_locked": row.entry_price_locked,
            "qty": qty,
            "trade_on": bool(qty) and qty > 0,
            "stop_now": row.stop_now,
            "exit_close_threshold": row.exit_close_threshold,
            "breakeven_active": row.breakeven_active,
            "euphoria_on": row.euphoria_on,
            "note": row.note,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

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

# Back-compat for callers expecting the old class name (alerts/unit_of_work/tests)
SqlPositionsRepo = PositionsRepo
