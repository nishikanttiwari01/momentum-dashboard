from __future__ import annotations

import sqlite3

import pytest

from routine import state
from routine.sizing import TradePlan


class FakeIdea:
    def __init__(self, symbol, pbss=18):
        self.symbol = symbol
        self.pbss = pbss
        self.score = 70
        self.close = 100.0
        self.conviction = "WATCH"
        self.plan = TradePlan(entry=100.0, stop=96.0, t1=110.0, t2=120.0,
                              qty=10, risk_rupees=40, position_rupees=1000)


@pytest.fixture
def conn(tmp_path):
    return state.connect(tmp_path / "t.db")


CAL = [f"2026-01-{d:02d}" for d in range(1, 31)]


def prices(table):
    def lookup(symbol, day):
        return table.get((symbol, day))
    return lookup


def test_record_alerts_idempotent(conn):
    ideas = [FakeIdea("AAA"), FakeIdea("BBB")]
    state.record_alerts(conn, "2026-01-05", ideas)
    state.record_alerts(conn, "2026-01-05", ideas)  # duplicate day: ignored
    n = conn.execute("SELECT COUNT(*) c FROM alerts").fetchone()["c"]
    assert n == 2


def test_recent_alert_symbols(conn):
    state.record_alerts(conn, CAL[10], [FakeIdea("AAA")])
    recent = state.recent_alert_symbols(conn, CAL[: 13], cooldown_days=5)
    assert "AAA" in recent
    old = state.recent_alert_symbols(conn, CAL, cooldown_days=5)  # window CAL[-5:] starts day 26
    assert "AAA" not in old


def test_label_outcomes(conn):
    state.record_alerts(conn, CAL[0], [FakeIdea("AAA")])
    table = {("AAA", CAL[0]): 100.0, ("AAA", CAL[5]): 105.0, ("AAA", CAL[21]): 120.0}
    n = state.label_outcomes(conn, prices(table), CAL)
    assert n == 1
    row = conn.execute("SELECT * FROM alerts").fetchone()
    assert abs(row["fwd5"] - 5.0) < 1e-9
    assert abs(row["fwd21"] - 20.0) < 1e-9
    stats = state.outcome_stats(conn)
    assert stats["n"] == 1 and stats["hit10_pct"] == 100.0


def test_label_waits_for_window(conn):
    state.record_alerts(conn, CAL[-3], [FakeIdea("AAA")])  # too recent
    n = state.label_outcomes(conn, prices({}), CAL)
    assert n == 0


def _open(conn, sym, entry, stop, t1, t2, day):
    conn.execute(
        "INSERT INTO trades (symbol, entry_date, entry_price, qty, stop, t1, t2)"
        " VALUES (?,?,?,?,?,?,?)", (sym, day, entry, 10, stop, t1, t2))
    conn.commit()


def test_exit_stop(conn):
    _open(conn, "AAA", 100, 96, 110, 120, CAL[0])
    ev = state.check_exits(conn, prices({("AAA", CAL[3]): 95.0}), CAL[3], CAL)
    assert len(ev) == 1 and ev[0].reason == "STOP" and ev[0].action == "SELL_ALL"
    assert ev[0].pnl_pct < 0


def test_exit_targets_and_priority(conn):
    _open(conn, "AAA", 100, 96, 110, 120, CAL[0])
    ev = state.check_exits(conn, prices({("AAA", CAL[3]): 111.0}), CAL[3], CAL)
    assert ev[0].reason == "T1" and ev[0].action == "BOOK_PARTIAL"
    ev = state.check_exits(conn, prices({("AAA", CAL[3]): 121.0}), CAL[3], CAL)
    assert ev[0].reason == "T2" and ev[0].action == "SELL_ALL"


def test_exit_timeout(conn):
    _open(conn, "AAA", 100, 96, 110, 120, CAL[0])
    ev = state.check_exits(conn, prices({("AAA", CAL[25]): 101.0}), CAL[25], CAL, timeout_days=20)
    assert ev[0].reason == "TIMEOUT"


def test_no_exit_when_in_range(conn):
    _open(conn, "AAA", 100, 96, 110, 120, CAL[0])
    ev = state.check_exits(conn, prices({("AAA", CAL[3]): 105.0}), CAL[3], CAL)
    assert ev == []
