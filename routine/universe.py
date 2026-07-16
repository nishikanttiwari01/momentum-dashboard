"""Symbol universe for the daily routine.

Bootstraps from the newest daily snapshot of the legacy lake (symbol, name,
sector). Optional override: routine/routine_data/universe.txt (one symbol per
line) — useful to shrink to NIFTY500 or test with a handful.
"""
from __future__ import annotations

from typing import Dict, List

import pandas as pd

from . import data_io, routine_config


def load_universe() -> pd.DataFrame:
    """DataFrame[symbol, name, sector] uppercased, deduped."""
    override = routine_config.ROUTINE_DATA / "universe.txt"
    if override.exists():
        syms = [
            s.strip().upper()
            for s in override.read_text(encoding="utf-8").splitlines()
            if s.strip() and not s.startswith("#")
        ]
        return pd.DataFrame({"symbol": syms, "name": syms, "sector": ""})

    dates = data_io.list_snapshot_dates()
    if not dates:
        raise RuntimeError(
            "No snapshot history found and no universe.txt override — "
            "cannot determine symbol universe."
        )
    snap = data_io.load_snapshot(dates[-1], columns=["symbol", "name", "sector"])
    # lake stores Yahoo-style tickers ("ABDL.NS"); canonical internal = bare NSE symbol
    snap["symbol"] = snap["symbol"].astype(str).str.upper().str.replace(r"\.NS$", "", regex=True)
    snap = snap.drop_duplicates("symbol")
    return snap.reset_index(drop=True)


def sector_map() -> Dict[str, str]:
    u = load_universe()
    return {r.symbol: (r.sector if isinstance(r.sector, str) else "") for r in u.itertuples()}


def yahoo_ticker(symbol: str) -> str:
    """NSE symbol -> Yahoo ticker. Index tickers (^...) pass through."""
    if symbol.startswith("^") or symbol.upper().endswith(".NS"):
        return symbol
    return f"{symbol}.NS"


def from_yahoo_ticker(ticker: str) -> str:
    if ticker.startswith("^"):
        return ticker
    return ticker[:-3] if ticker.upper().endswith(".NS") else ticker
