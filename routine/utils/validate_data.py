"""Dev utility: data-quality gate for the snapshot panel.

Checks that would silently corrupt a backtest:
- duplicate (as_of, symbol) rows
- non-positive / missing closes
- absurd 1-day moves (>40%) that usually mean unadjusted splits
- symbols that appear/disappear frequently (universe churn)

Usage: python -m routine.utils.validate_data [--start 2025-01-01]
Exit code 1 if any ERROR-level issue found.
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from .. import data_io


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--start", help="ISO date lower bound")
    p.add_argument("--end", help="ISO date upper bound")
    args = p.parse_args(argv)

    dates = data_io.list_snapshot_dates()
    if args.start:
        dates = [d for d in dates if d >= args.start]
    if args.end:
        dates = [d for d in dates if d <= args.end]
    print(f"validating {len(dates)} snapshot dates ...")
    panel = data_io.load_feature_panel(dates=dates, columns=["symbol", "close", "median_traded_value_20d"])

    errors = 0

    dupes = panel.duplicated(subset=["as_of", "symbol"]).sum()
    print(f"[{'ERROR' if dupes else 'ok':>5}] duplicate (as_of,symbol) rows: {dupes}")
    errors += bool(dupes)

    close = pd.to_numeric(panel["close"], errors="coerce")
    bad_close = int((close.isna() | (close <= 0)).sum())
    pct = bad_close / max(len(panel), 1) * 100
    lvl = "ERROR" if pct > 2 else "ok"
    print(f"[{lvl:>5}] missing/non-positive closes: {bad_close} ({pct:.2f}%)")
    errors += lvl == "ERROR"

    m = data_io.close_matrix(panel)
    rets = m.pct_change(fill_method=None)
    wild = (rets.abs() > 0.40).sum().sum()
    total = rets.notna().sum().sum()
    pct = wild / max(total, 1) * 100
    lvl = "WARN " if pct < 0.05 else "ERROR"
    print(f"[{lvl:>5}] daily moves >40% (possible unadjusted splits/bad ticks): {int(wild)} ({pct:.3f}%)")
    errors += lvl == "ERROR"

    days_per_symbol = panel.groupby("symbol")["as_of"].nunique()
    flaky = int((days_per_symbol < len(dates) * 0.5).sum())
    print(f"[{'ok':>5}] symbols present <50% of days (universe churn, info only): {flaky} of {len(days_per_symbol)}")

    print("\nRESULT:", "FAIL" if errors else "PASS")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
