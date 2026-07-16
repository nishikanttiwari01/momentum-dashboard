"""One-time bootstrap: legacy snapshot lake -> per-symbol OHLCV store.

Gives the routine instant history (indicators need 240+ bars) instead of
waiting for a yfinance backfill. After this, daily fetch keeps it current.
Note: snapshots carry unadjusted OHLC; adj_close is set to close. Good
enough to start — yfinance rows will overwrite going forward.

Usage: python -m routine.utils.bootstrap_from_lake [--min-days 240]
"""
from __future__ import annotations

import argparse
import logging

import pandas as pd

from .. import data_io, fetch, routine_config

log = logging.getLogger(__name__)

COLS = ["symbol", "open", "high", "low", "close", "last", "volume"]


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--min-days", type=int, default=240, help="skip symbols with less history")
    p.add_argument("--limit", type=int, default=0, help="only first N symbols (testing)")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    routine_config.ensure_dirs()
    dates = data_io.list_snapshot_dates()
    log.info("loading %d snapshot dates ...", len(dates))
    panel = data_io.load_feature_panel(dates=dates, columns=COLS)
    panel["date"] = pd.to_datetime(panel["as_of"]).dt.date
    for c in ("open", "high", "low", "close", "volume"):
        panel[c] = pd.to_numeric(panel[c], errors="coerce")
    panel = panel.dropna(subset=["close"])  # close already coalesced with `last` by data_io
    # Pre-2026-05 snapshots have no OHLC/volume: approximate bars with close.
    for c in ("open", "high", "low"):
        panel[c] = panel[c].fillna(panel["close"])
    panel["volume"] = panel["volume"].fillna(0.0)

    written = skipped = 0
    symbols = panel["symbol"].unique()
    if args.limit:
        symbols = symbols[: args.limit]
    from .. import universe as uni_mod

    wanted = set(symbols)
    for sym, g in panel.groupby("symbol", sort=False):
        if sym not in wanted:
            continue
        if len(g) < args.min_days:
            skipped += 1
            continue
        df = g[["date", "open", "high", "low", "close", "volume"]].copy()
        df["adj_close"] = df["close"]
        df = df[["date", "open", "high", "low", "close", "adj_close", "volume"]]
        store_sym = uni_mod.from_yahoo_ticker(sym)  # lake uses "X.NS"; store bare symbol
        existing = fetch.load_ohlcv(store_sym)
        fetch.save_ohlcv(store_sym, fetch.merge_new_bars(existing, df))
        written += 1
    print(f"bootstrapped {written} symbols ({skipped} skipped for <{args.min_days} days)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
