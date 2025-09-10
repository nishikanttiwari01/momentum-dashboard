from __future__ import annotations
from sqlalchemy.orm import Session
from sqlalchemy import select, delete

from ..models import Watchlist
from ..interfaces.base import IWatchlistRepo


class SqlWatchlistRepo(IWatchlistRepo):
    def __init__(self, session: Session):
        self.s = session

    def list_symbols(self) -> list[str]:
        rows = self.s.execute(select(Watchlist.symbol).order_by(Watchlist.symbol.asc())).all()
        return [r[0] for r in rows]

    def upsert_symbol(self, symbol: str, note: str | None = None) -> None:
        symbol = symbol.upper()
        row = self.s.query(Watchlist).filter(Watchlist.symbol == symbol).one_or_none()
        if row:
            row.note = note
        else:
            self.s.add(Watchlist(symbol=symbol, note=note))

    def remove_symbol(self, symbol: str) -> None:
        self.s.execute(delete(Watchlist).where(Watchlist.symbol == symbol.upper()))
