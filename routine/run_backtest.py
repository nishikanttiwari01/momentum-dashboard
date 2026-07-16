"""CLI entrypoint: replay history, measure PBSS/score edge, write report.

Usage (from repo root, venv active):
    python -m routine.run_backtest
    python -m routine.run_backtest --start 2025-01-01 --liquidity-floor 20000000
    python -m routine.run_backtest --thresholds 14 16 18 20
"""
from __future__ import annotations

import argparse
import logging
import sys

from . import config, data_io, report
from .backtest import run_backtest


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="PBSS/score backtest over parquet history")
    p.add_argument("--start", help="ISO date lower bound (inclusive)")
    p.add_argument("--end", help="ISO date upper bound (inclusive)")
    p.add_argument("--liquidity-floor", type=float, default=None, help="rupees/day, default 1cr")
    p.add_argument("--thresholds", type=int, nargs="+", default=None, help="PBSS thresholds")
    p.add_argument("--cooldown", type=int, default=None, help="episode cooldown (TD)")
    p.add_argument("--no-save", action="store_true", help="print only")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    cfg = config.BacktestConfig()
    if args.liquidity_floor is not None:
        cfg.liquidity_floor_rupees = args.liquidity_floor
    if args.thresholds:
        cfg.pbss_thresholds = tuple(sorted(args.thresholds))
    if args.cooldown is not None:
        cfg.cooldown_days = args.cooldown

    dates = data_io.list_snapshot_dates()
    if args.start:
        dates = [d for d in dates if d >= args.start]
    if args.end:
        dates = [d for d in dates if d <= args.end]
    if len(dates) < 60:
        print(f"ERROR: only {len(dates)} usable snapshot dates — not enough to backtest.", file=sys.stderr)
        return 2

    res = run_backtest(cfg=cfg, dates=dates)
    print(report.render_text(res))
    if not args.no_save:
        out = report.save(res)
        print(f"\nsaved: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
