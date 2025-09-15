from sqlalchemy.orm import Session
from ..models import DrawerState

class DrawerStateRepo:
    def __init__(self, session: Session): self.s = session

    def upsert(self, symbol: str, **kwargs) -> None:
        row = self.s.query(DrawerState).filter_by(symbol=symbol).first()
        if row is None:
            row = DrawerState(symbol=symbol, **kwargs)
            self.s.add(row)
        else:
            for k, v in kwargs.items(): setattr(row, k, v)

    def get(self, symbol: str) -> DrawerState | None:
        return self.s.query(DrawerState).filter_by(symbol=symbol).first()
