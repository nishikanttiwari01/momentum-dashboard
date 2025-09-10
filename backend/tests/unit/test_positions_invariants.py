from __future__ import annotations
from app.core.db import init_sqlite, get_sessionmaker
from app.repos.unit_of_work import SqliteUnitOfWork

def test_stop_never_decreases(tmp_path):
    init_sqlite("./data/test_invariants.db")
    uow = SqliteUnitOfWork(get_sessionmaker())
    with uow:
        uow.positions.lock_entry("RELIANCE", 100.0, 10)
        uow.positions.update_stop("RELIANCE", 95.0)
        # Attempt to lower stop
        uow.positions.update_stop("RELIANCE", 90.0)
        pos = [p for p in uow.positions.list_positions() if p["symbol"] == "RELIANCE"][0]
        assert pos["stop_now"] == 95.0
