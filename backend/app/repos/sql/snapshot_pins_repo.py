from __future__ import annotations
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, delete

from ..models import SnapshotPin
from ..interfaces.base import ISnapshotPinsRepo


class SnapshotPinsRepo(ISnapshotPinsRepo):
    def __init__(self, session: Session | None = None):   # <-- allow None
        self.s = session

    def pin(self, symbol: str, run_id: str) -> None:
        symbol = symbol.upper()
        row = self.s.query(SnapshotPin).filter(SnapshotPin.symbol == symbol).one_or_none()
        if row:
            row.run_id = run_id
        else:
            self.s.add(SnapshotPin(symbol=symbol, run_id=run_id))

    def unpin(self, symbol: str) -> None:
        self.s.execute(delete(SnapshotPin).where(SnapshotPin.symbol == symbol.upper()))

    def get_pins(self) -> dict[str, str]:
        rows = self.s.execute(select(SnapshotPin.symbol, SnapshotPin.run_id)).all()
        return {r[0]: r[1] for r in rows}

    # Phase 8: minimal addition
    def get(self, symbol: str) -> Optional[str]:
        # Safe when no DB wired
        if self.s is None:
            return None
        symbol = symbol.upper()
        row = self.s.query(SnapshotPin).filter(SnapshotPin.symbol == symbol).one_or_none()
        return row.run_id if row else None
    
SqlSnapshotPinsRepo = SnapshotPinsRepo