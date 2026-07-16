"""SQLite state: alerts fired, open trades, exits, and outcome labeling.

Tables:
  alerts(fired_date, symbol, pbss, score, close, entry, stop, t1, t2, qty,
         conviction, fwd5, fwd21, labeled)
  trades(symbol, entry_date, entry_price, qty, stop, t1, t2, status,
         exit_date, exit_price, exit_reason)

CLI (manual trade booking after you actually place an order):
    python -m routine.state open RELIANCE 2891.5 10 --stop 2750 --t1 3180 --t2 3470
    python -m routine.state close RELIANCE 3050 --reason MANUAL
    python -m routine.state list
"""
from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

from . import routine_config

SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
  id INTEGER PRIMARY KEY,
  fired_date TEXT NOT NULL,
  symbol TEXT NOT NULL,
  pbss INTEGER, score INTEGER, close REAL,
  entry REAL, stop REAL, t1 REAL, t2 REAL, qty INTEGER,
  conviction TEXT,
  fwd5 REAL, fwd21 REAL, labeled INTEGER DEFAULT 0,
  UNIQUE(fired_date, symbol)
);
CREATE TABLE IF NOT EXISTS trades (
  id INTEGER PRIMARY KEY,
  symbol TEXT NOT NULL,
  entry_date TEXT NOT NULL,
  entry_price REAL NOT NULL,
  qty INTEGER NOT NULL,
  stop REAL, t1 REAL, t2 REAL,
  status TEXT NOT NULL DEFAULT 'OPEN',
  exit_date TEXT, exit_price REAL, exit_reason TEXT
);
"""


def connect(db_path: Optional[Path] = None) -> sqlite3.Connection:
    routine_config.ensure_dirs()
    conn = sqlite3.connect(str(db_path or routine_config.DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


# ---------------------------------------------------------------------------
# Alerts + outcomes
# ---------------------------------------------------------------------------

def record_alerts(conn: sqlite3.Connection, fired_date: str, ideas) -> int:
    n = 0
    for i in ideas:
        try:
            conn.execute(
                "INSERT OR IGNORE INTO alerts (fired_date, symbol, pbss, score, close,"
                " entry, stop, t1, t2, qty, conviction) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (fired_date, i.symbol, i.pbss, i.score, i.close, i.plan.entry,
                 i.plan.stop, i.plan.t1, i.plan.t2, i.plan.qty, i.conviction),
            )
            n += conn.total_changes > 0
        except sqlite3.Error:
            pass
    conn.commit()
    return n


def recent_alert_symbols(conn: sqlite3.Connection, calendar: List[str], cooldown_days: int) -> set:
    """Symbols alerted within the last `cooldown_days` trading days."""
    if not calendar:
        return set()
    cutoff = calendar[-cooldown_days:] if len(calendar) >= cooldown_days else calendar
    rows = conn.execute(
        f"SELECT DISTINCT symbol FROM alerts WHERE fired_date >= ?", (cutoff[0],)
    ).fetchall()
    return {r["symbol"] for r in rows}


def label_outcomes(conn: sqlite3.Connection, price_lookup, calendar: List[str]) -> int:
    """Fill fwd5/fwd21 for alerts old enough. price_lookup(symbol, date_iso)->close|None."""
    pos = {d: i for i, d in enumerate(calendar)}
    labeled = 0
    rows = conn.execute("SELECT * FROM alerts WHERE labeled = 0").fetchall()
    for r in rows:
        p0 = pos.get(r["fired_date"])
        if p0 is None:
            continue
        base = price_lookup(r["symbol"], r["fired_date"])
        if not base:
            continue
        updates = {}
        for col, w in (("fwd5", 5), ("fwd21", 21)):
            if p0 + w < len(calendar):
                px = price_lookup(r["symbol"], calendar[p0 + w])
                if px:
                    updates[col] = (px / base - 1.0) * 100.0
        if "fwd21" in updates:
            conn.execute(
                "UPDATE alerts SET fwd5 = ?, fwd21 = ?, labeled = 1 WHERE id = ?",
                (updates.get("fwd5"), updates["fwd21"], r["id"]),
            )
            labeled += 1
        elif "fwd5" in updates:
            conn.execute("UPDATE alerts SET fwd5 = ? WHERE id = ?", (updates["fwd5"], r["id"]))
    conn.commit()
    return labeled


def outcome_stats(conn: sqlite3.Connection) -> Optional[Dict]:
    row = conn.execute(
        "SELECT COUNT(*) n, AVG(fwd21) avg21,"
        " SUM(CASE WHEN fwd21 >= 10 THEN 1 ELSE 0 END)*100.0/COUNT(*) hit10,"
        " SUM(CASE WHEN fwd21 > 0 THEN 1 ELSE 0 END)*100.0/COUNT(*) win"
        " FROM alerts WHERE labeled = 1"
    ).fetchone()
    if not row or not row["n"]:
        return None
    return {"n": row["n"], "avg_fwd21": row["avg21"], "hit10_pct": row["hit10"], "win_pct": row["win"]}


# ---------------------------------------------------------------------------
# Trades + exit checks
# ---------------------------------------------------------------------------

@dataclass
class ExitEvent:
    symbol: str
    reason: str        # STOP | T1 | T2 | TIMEOUT
    action: str        # SELL_ALL | BOOK_PARTIAL
    price: float
    pnl_pct: float
    detail: str


def open_trades(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    return conn.execute("SELECT * FROM trades WHERE status = 'OPEN' ORDER BY entry_date").fetchall()


def check_exits(conn: sqlite3.Connection, price_lookup, today_iso: str,
                calendar: List[str], timeout_days: int = 20) -> List[ExitEvent]:
    """EOD exit rules on open trades. Emits instructions; closing in the DB is
    manual (you confirm you actually sold) except nothing auto-closes here."""
    pos = {d: i for i, d in enumerate(calendar)}
    events: List[ExitEvent] = []
    for t in open_trades(conn):
        px = price_lookup(t["symbol"], today_iso)
        if not px:
            continue
        pnl = (px / t["entry_price"] - 1.0) * 100.0
        if t["stop"] and px <= t["stop"]:
            events.append(ExitEvent(t["symbol"], "STOP", "SELL_ALL", px, pnl,
                                    f"close {px:.2f} <= stop {t['stop']:.2f}"))
            continue
        if t["t2"] and px >= t["t2"]:
            events.append(ExitEvent(t["symbol"], "T2", "SELL_ALL", px, pnl,
                                    f"target T2 {t['t2']:.2f} reached"))
            continue
        if t["t1"] and px >= t["t1"]:
            events.append(ExitEvent(t["symbol"], "T1", "BOOK_PARTIAL", px, pnl,
                                    f"target T1 {t['t1']:.2f} reached — book half, trail rest"))
            continue
        p_entry, p_today = pos.get(t["entry_date"]), pos.get(today_iso)
        if p_entry is not None and p_today is not None and (p_today - p_entry) >= timeout_days:
            events.append(ExitEvent(t["symbol"], "TIMEOUT", "SELL_ALL", px, pnl,
                                    f"{p_today - p_entry} trading days without target"))
    return events


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="trade state")
    sub = p.add_subparsers(dest="cmd", required=True)
    po = sub.add_parser("open")
    po.add_argument("symbol"); po.add_argument("price", type=float); po.add_argument("qty", type=int)
    po.add_argument("--stop", type=float); po.add_argument("--t1", type=float); po.add_argument("--t2", type=float)
    po.add_argument("--date", default=date.today().isoformat())
    pc = sub.add_parser("close")
    pc.add_argument("symbol"); pc.add_argument("price", type=float)
    pc.add_argument("--reason", default="MANUAL"); pc.add_argument("--date", default=date.today().isoformat())
    sub.add_parser("list")
    args = p.parse_args(argv)

    conn = connect()
    if args.cmd == "open":
        conn.execute(
            "INSERT INTO trades (symbol, entry_date, entry_price, qty, stop, t1, t2)"
            " VALUES (?,?,?,?,?,?,?)",
            (args.symbol.upper(), args.date, args.price, args.qty, args.stop, args.t1, args.t2),
        )
        conn.commit()
        print(f"opened {args.symbol.upper()} x{args.qty} @ {args.price}")
    elif args.cmd == "close":
        cur = conn.execute(
            "UPDATE trades SET status='CLOSED', exit_date=?, exit_price=?, exit_reason=?"
            " WHERE symbol=? AND status='OPEN'",
            (args.date, args.price, args.reason, args.symbol.upper()),
        )
        conn.commit()
        print(f"closed {cur.rowcount} position(s) in {args.symbol.upper()} @ {args.price}")
    else:
        for t in open_trades(conn):
            print(dict(t))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
