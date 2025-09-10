from __future__ import annotations
from sqlalchemy.orm import Session
from sqlalchemy import select, delete

from ..models import SnapshotPin
from ..interfaces.base import ISnapshotPinsRepo


class SqlSnapshotPinsRepo(ISnapshotPinsRepo):
    def __init__(self, session: Session):
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
