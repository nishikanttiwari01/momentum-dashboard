from __future__ import annotations
import pytest
from app.core.db import init_sqlite, get_sessionmaker
from app.repos.unit_of_work import SqliteUnitOfWork

def test_stop_never_decreases(tmp_path):
    db_path = tmp_path / "positions_stop.db"
    init_sqlite(str(db_path))
    uow = SqliteUnitOfWork(get_sessionmaker())
    with uow:
        uow.positions.lock_entry("RELIANCE", 100.0, 10)
        uow.positions.update_stop("RELIANCE", 95.0)
        # Attempt to lower stop
        uow.positions.update_stop("RELIANCE", 90.0)
        pos = [p for p in uow.positions.list_positions() if p["symbol"] == "RELIANCE"][0]
        assert pos["stop_now"] == 95.0

def test_close_and_reopen_records_history(tmp_path):
    db_path = tmp_path / "positions_close.db"
    init_sqlite(str(db_path))
    uow = SqliteUnitOfWork(get_sessionmaker())
    with uow:
        closed = uow.positions.create_or_lock(symbol="RELIANCE", price=100.0, qty=10)
        updated = uow.positions.update_by_id(
            closed["id"],
            trade_on=False,
            sell_price=110.0,
        )
        assert updated is not None
        rows = uow.positions.list_positions()
        assert len(rows) == 1
        record = rows[0]
        assert record["trade_on"] is False
        assert record["sell_price"] == pytest.approx(110.0)
        assert record["sold_at"] is not None
        assert record["realized_pl"] == pytest.approx(100.0)
        assert record["realized_pl_pct"] == pytest.approx(10.0)

        reopened = uow.positions.create_or_lock(symbol="RELIANCE", price=120.0, qty=5)
        assert reopened["id"] != record["id"]
        assert reopened["trade_on"] is True
        all_rows = uow.positions.list_positions()
        assert len(all_rows) == 2
        active_rows = [r for r in all_rows if r["trade_on"]]
        assert len(active_rows) == 1
