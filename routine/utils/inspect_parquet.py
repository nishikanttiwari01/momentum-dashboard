"""Dev utility: what's actually in the parquet lake?

Reports partition counts, date range, calendar gaps, schema evolution
(which key columns appear/disappear over time), and null rates.

Usage: python -m routine.utils.inspect_parquet [--samples 8]
"""
from __future__ import annotations

import argparse
import glob
from datetime import date, timedelta

import pyarrow.parquet as pq

from .. import config, data_io

KEY_COLUMNS = [
    "close", "score", "pre_breakout_score", "vol_z20", "relvol20",
    "obv_above_ma", "ret_5d", "rsi14", "adx14", "proximity_52w_high_pct",
    "pivot_clear_pct", "median_traded_value_20d", "sector",
]


def weekday_gaps(dates: list) -> list:
    """ISO weekdays missing between first and last snapshot (rough holiday/gap check)."""
    if len(dates) < 2:
        return []
    have = set(dates)
    d0 = date.fromisoformat(dates[0])
    d1 = date.fromisoformat(dates[-1])
    missing = []
    cur = d0
    while cur <= d1:
        if cur.weekday() < 5 and cur.isoformat() not in have:
            missing.append(cur.isoformat())
        cur += timedelta(days=1)
    return missing


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--samples", type=int, default=8, help="snapshots to sample for schema/null checks")
    args = p.parse_args(argv)

    base = config.scores_daily_dir()
    print(f"root: {base}")
    all_parts = sorted(glob.glob(str(base / "as_of=*")))
    dates = data_io.list_snapshot_dates()
    print(f"partitions: {len(all_parts)}  with data: {len(dates)}  empty: {len(all_parts) - len(dates)}")
    if not dates:
        print("NO USABLE DATA")
        return 1
    print(f"range: {dates[0]} -> {dates[-1]}")

    gaps = weekday_gaps(dates)
    print(f"weekday gaps (holidays or missed runs): {len(gaps)}")
    if gaps:
        print("  last 10:", gaps[-10:])

    # schema evolution + null rates on evenly spaced samples
    step = max(len(dates) // args.samples, 1)
    sample_days = dates[::step][: args.samples] + [dates[-1]]
    print(f"\n{'date':<12} {'rows':>6}  missing_columns / null% of key columns")
    for day in sample_days:
        files = sorted(glob.glob(str(base / f"as_of={day}" / "**" / "*.parquet"), recursive=True))
        pf = pq.ParquetFile(files[-1])
        names = set(pf.schema_arrow.names)
        present = [c for c in KEY_COLUMNS if c in names]
        absent = [c for c in KEY_COLUMNS if c not in names]
        df = pf.read(columns=present).to_pandas()
        nulls = {c: round(df[c].isna().mean() * 100) for c in present if df[c].isna().mean() > 0.05}
        print(f"{day:<12} {len(df):>6}  absent={absent or '-'}  nulls>{5}%={nulls or '-'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
