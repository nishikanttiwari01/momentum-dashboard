from sqlalchemy.orm import Session
from ..models import SnapshotPin

class PinsRepo:
    def __init__(self, session: Session): self.s = session

    def get_pinned_run_id(self, symbol: str) -> str | None:
        row = (self.s.query(SnapshotPin)
               .filter(SnapshotPin.symbol == symbol)
               .order_by(SnapshotPin.id.desc())
               .first())
        return row.pinned_run_id if row else None

    def set_pin(self, symbol: str, run_id: str, reason: str | None = None) -> None:
        self.s.add(SnapshotPin(symbol=symbol, pinned_run_id=run_id, reason=reason))
