from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Iterable

from sqlalchemy.orm import Session

from ..models import Position
from ..interfaces.base import IPositionsRepo


class PositionsRepo(IPositionsRepo):
    def __init__(self, session: Session | None = None):
        self.s = session  # per-request session injected by dependency

    # ----- Reads -----

    def list_positions(self, *, symbol: str | None = None) -> list[dict]:
        q = self.s.query(Position)
        if symbol:
            q = q.filter(Position.symbol == symbol.upper())
        rows: Iterable[Position] = q.order_by(Position.symbol.asc()).all()
        return [self._row_to_dict(r) for r in rows]

    def get(self, symbol: str) -> Optional[Dict[str, Any]]:
        if self.s is None:
            return None
        row = (
            self.s.query(Position)
            .filter(Position.symbol == symbol.upper())
            .one_or_none()
        )
        return self._row_to_dict(row) if row else None

    def get_by_id(self, id_: int) -> Optional[Dict[str, Any]]:
        row = self.s.query(Position).filter(Position.id == id_).one_or_none()
        return self._row_to_dict(row) if row else None

    # ----- Writes -----

    def create_or_lock(
        self,
        *,
        symbol: str,
        price: float,
        qty: int | None = None,
        note: str | None = None,
    ) -> Dict[str, Any]:
        """
        Create (or update existing) position row and LOCK entry.
        Idempotent: if already exists, sets trade_on=True and entry_price_locked=price only if previously NULL.
        """
        now = datetime.utcnow()
        symbol = symbol.upper()
        row = self.s.query(Position).filter(Position.symbol == symbol).one_or_none()
        if row:
            if row.entry_price_locked is None:
                row.entry_price_locked = float(price)
            row.trade_on = True
            if qty is not None:
                row.qty = qty
            if note is not None:
                row.note = note
            row.updated_at = now
        else:
            row = Position(
                symbol=symbol,
                entry_price_locked=float(price),
                qty=qty,
                trade_on=True,
                stop_now=None,
                exit_close_threshold=None,
                breakeven_active=False,
                euphoria_on=False,
                note=note,
            )
            self.s.add(row)
        self.s.flush()
        self.s.commit()  # ✅ make visible to subsequent requests
        return self._row_to_dict(row)

    # (optional legacy) upsert retained for backward-compat callers
    def upsert(
        self,
        *,
        symbol: str,
        price: float,
        as_of: Optional[str] = None,
        note: Optional[str] = None,
        qty: Optional[int] = None,
    ) -> Dict[str, Any]:
        return self.create_or_lock(symbol=symbol, price=price, qty=qty, note=note)

    def update_by_id(self, id_: int, **fields) -> Optional[Dict[str, Any]]:
        """
        Partial updates: qty, stop_now, exit_close_threshold, breakeven_active,
        euphoria_on, note, trade_on. (entry_price_locked changes are not allowed)
        """
        row = self.s.query(Position).filter(Position.id == id_).one_or_none()
        if not row:
            return None
        fields.pop("entry_price_locked", None)

        upd = False
        for k, v in fields.items():
            if not hasattr(row, k):
                continue
            setattr(row, k, v)
            upd = True
        if upd:
            row.updated_at = datetime.utcnow()
            self.s.flush()
            self.s.commit()  # ✅
        return self._row_to_dict(row)

    def unlock_by_id(self, id_: int) -> bool:
        """
        Soft unlock: clear locked entry and set trade_on=False.
        """
        row = self.s.query(Position).filter(Position.id == id_).one_or_none()
        if not row:
            return False
        row.entry_price_locked = None
        row.trade_on = False
        row.updated_at = datetime.utcnow()
        self.s.flush()
        self.s.commit()  # ✅
        return True

    def delete(self, id_: int) -> bool:
        """
        Hard remove (alternative unlock).
        """
        row = self.s.query(Position).filter(Position.id == id_).one_or_none()
        if not row:
            return False
        self.s.delete(row)
        self.s.flush()
        self.s.commit()  # ✅
        return True

    # ----- Helpers -----

    def _aware_utc(self, dt: datetime | None) -> datetime | None:
        """Ensure tz-aware UTC datetimes for Pydantic v2 models."""
        if dt is None:
            return None
        if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    def _row_to_dict(self, r: Position | None) -> Optional[Dict[str, Any]]:
        if r is None:
            return None
        return {
            "id": r.id,
            "symbol": r.symbol,
            "entry_price_locked": r.entry_price_locked,
            "qty": r.qty,
            "stop_now": r.stop_now,
            "exit_close_threshold": r.exit_close_threshold,
            "breakeven_active": r.breakeven_active,
            "euphoria_on": r.euphoria_on,
            "trade_on": r.trade_on,
            "note": r.note,
            "created_at": self._aware_utc(r.created_at),
            "updated_at": self._aware_utc(r.updated_at),
        }

    # Back-compat helper used elsewhere
    def update_stop(self, symbol: str, stop_now: float) -> None:
        symbol = symbol.upper()
        row = self.s.query(Position).filter(Position.symbol == symbol).one_or_none()
        if row is None:
            return
        if row.stop_now is None or float(stop_now) > float(row.stop_now):
            row.stop_now = float(stop_now)
            row.updated_at = datetime.utcnow()
            self.s.flush()
            self.s.commit()  # ✅

    def close_position(self, symbol: str, reason: str) -> None:
        row = self.s.query(Position).filter(Position.symbol == symbol.upper()).one_or_none()
        if row:
            self.s.delete(row)
            self.s.flush()
            self.s.commit()  # ✅


# Back-compat for callers expecting the old class name
SqlPositionsRepo = PositionsRepo
