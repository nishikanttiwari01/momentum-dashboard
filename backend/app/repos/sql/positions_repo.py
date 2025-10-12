from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Dict, Any, Iterable

from sqlalchemy.orm import Session

from ..models import Position
from ..interfaces.base import IPositionsRepo


class PositionsRepo(IPositionsRepo):
    def __init__(self, session: Session | None = None):
        self.s = session  # per-request session injected by dependency

    # ----- Internal helpers -----

    def _session(self) -> Session:
        if self.s is None:
            raise RuntimeError("PositionsRepo requires a session for write operations")
        return self.s

    @staticmethod
    def _canon_symbol(symbol: str) -> str:
        return symbol.upper()

    @staticmethod
    def _utcnow_naive() -> datetime:
        return datetime.utcnow()

    @staticmethod
    def _to_naive_utc(dt: datetime | None) -> datetime | None:
        if dt is None:
            return None
        if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
            return dt
        return dt.astimezone(timezone.utc).replace(tzinfo=None)

    # ----- Reads -----

    def list_positions(
        self,
        *,
        symbol: str | None = None,
        active: bool | None = None,
    ) -> list[dict]:
        if self.s is None:
            return []
        q = self.s.query(Position)
        if symbol:
            q = q.filter(Position.symbol == self._canon_symbol(symbol))
        if active is not None:
            q = q.filter(Position.trade_on == bool(active))
        rows: Iterable[Position] = (
            q.order_by(
                Position.trade_on.desc(),
                Position.created_at.desc(),
                Position.id.desc(),
            ).all()
        )
        return [self._row_to_dict(r) for r in rows]

    def get(self, symbol: str) -> Optional[Dict[str, Any]]:
        if self.s is None:
            return None
        row = (
            self.s.query(Position)
            .filter(
                Position.symbol == self._canon_symbol(symbol),
                Position.trade_on.is_(True),
            )
            .order_by(Position.created_at.desc(), Position.id.desc())
            .first()
        )
        return self._row_to_dict(row) if row else None

    def get_by_id(self, id_: int) -> Optional[Dict[str, Any]]:
        if self.s is None:
            return None
        row = self.s.query(Position).filter(Position.id == id_).one_or_none()
        return self._row_to_dict(row) if row else None

    # ----- Writes -----

    def lock_entry(self, symbol: str, price: float, qty: int | None = None) -> Dict[str, Any]:
        return self.create_or_lock(symbol=symbol, price=price, qty=qty)

    def create_or_lock(
        self,
        *,
        symbol: str,
        price: float,
        qty: int | None = None,
        note: str | None = None,
    ) -> Dict[str, Any]:
        session = self._session()
        now = self._utcnow_naive()
        symbol = self._canon_symbol(symbol)

        row = (
            session.query(Position)
            .filter(Position.symbol == symbol, Position.trade_on.is_(True))
            .order_by(Position.created_at.desc(), Position.id.desc())
            .first()
        )

        if row:
            row.entry_price_locked = float(price)
            row.trade_on = True
            if qty is not None:
                row.qty = qty
            if note is not None:
                row.note = note
            row.sell_price = None
            row.sold_at = None
            row.updated_at = now
        else:
            row = Position(
                symbol=symbol,
                entry_price_locked=float(price),
                qty=qty,
                stop_now=None,
                exit_close_threshold=None,
                breakeven_active=False,
                euphoria_on=False,
                trade_on=True,
                sell_price=None,
                sold_at=None,
                note=note,
            )
            session.add(row)
        session.flush()
        session.commit()
        return self._row_to_dict(row)

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
        session = self._session()
        row = session.query(Position).filter(Position.id == id_).one_or_none()
        if not row:
            return None

        fields.pop("entry_price_locked", None)

        updated = False

        def _assign(attr: str, value: Any):
            nonlocal updated
            setattr(row, attr, value)
            updated = True

        simple_fields = (
            "qty",
            "stop_now",
            "exit_close_threshold",
            "breakeven_active",
            "euphoria_on",
            "note",
        )
        for key in simple_fields:
            if key not in fields:
                continue
            value = fields[key]
            if value is None and key in {"breakeven_active", "euphoria_on"}:
                continue
            _assign(key, value)

        if "sell_price" in fields:
            value = fields["sell_price"]
            _assign("sell_price", float(value) if value is not None else None)

        if "sold_at" in fields:
            value = fields["sold_at"]
            _assign("sold_at", self._to_naive_utc(value) if value is not None else None)

        if "trade_on" in fields and fields["trade_on"] is not None:
            trade_on = bool(fields["trade_on"])
            if row.trade_on != trade_on:
                row.trade_on = trade_on
                updated = True
            if trade_on:
                row.sell_price = None
                row.sold_at = None
            else:
                if getattr(row, "sold_at", None) is None and fields.get("sold_at") is None:
                    row.sold_at = self._utcnow_naive()

        if not updated:
            return self._row_to_dict(row)

        row.updated_at = self._utcnow_naive()
        session.flush()
        session.commit()
        return self._row_to_dict(row)

    def unlock_by_id(self, id_: int) -> bool:
        """Legacy unlock retained for backward compatibility."""
        return self.update_by_id(id_, trade_on=False) is not None

    def delete(self, id_: int) -> bool:
        """
        Legacy delete now soft-closes the position to preserve history.
        """
        session = self._session()
        row = session.query(Position).filter(Position.id == id_).one_or_none()
        if not row:
            return False
        if row.trade_on:
            row.trade_on = False
            if row.sold_at is None:
                row.sold_at = self._utcnow_naive()
        row.updated_at = self._utcnow_naive()
        session.flush()
        session.commit()
        return True

    # ----- Helpers -----

    def _aware_utc(self, dt: datetime | None) -> datetime | None:
        """Ensure tz-aware UTC datetimes for Pydantic v2 models."""
        if dt is None:
            return None
        if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    def _realized_metrics(self, row: Position) -> tuple[float | None, float | None]:
        entry = row.entry_price_locked
        sell = row.sell_price
        qty = row.qty
        if entry is None or sell is None:
            return None, None
        diff = sell - entry
        amount = diff * qty if qty is not None else None
        pct = (diff / entry) * 100.0 if entry else None
        return amount, pct

    def _row_to_dict(self, r: Position | None) -> Optional[Dict[str, Any]]:
        if r is None:
            return None
        realized_amount, realized_pct = self._realized_metrics(r)
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
            "sell_price": r.sell_price,
            "sold_at": self._aware_utc(r.sold_at),
            "realized_pl": realized_amount,
            "realized_pl_pct": realized_pct,
            "note": r.note,
            "created_at": self._aware_utc(r.created_at),
            "updated_at": self._aware_utc(r.updated_at),
        }

    # Back-compat helper used elsewhere
    def update_stop(self, symbol: str, stop_now: float) -> None:
        if self.s is None:
            return
        row = (
            self.s.query(Position)
            .filter(
                Position.symbol == self._canon_symbol(symbol),
                Position.trade_on.is_(True),
            )
            .order_by(Position.created_at.desc(), Position.id.desc())
            .first()
        )
        if row is None:
            return
        if row.stop_now is None or float(stop_now) > float(row.stop_now):
            row.stop_now = float(stop_now)
            row.updated_at = self._utcnow_naive()
            self.s.flush()
            self.s.commit()

    def close_position(self, symbol: str, reason: str) -> None:
        if self.s is None:
            return
        row = (
            self.s.query(Position)
            .filter(
                Position.symbol == self._canon_symbol(symbol),
                Position.trade_on.is_(True),
            )
            .order_by(Position.created_at.desc(), Position.id.desc())
            .first()
        )
        if not row:
            return
        row.trade_on = False
        if row.sold_at is None:
            row.sold_at = self._utcnow_naive()
        row.updated_at = self._utcnow_naive()
        self.s.flush()
        self.s.commit()


# Back-compat for callers expecting the old class name
SqlPositionsRepo = PositionsRepo
