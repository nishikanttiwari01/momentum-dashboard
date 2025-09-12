# app/tools/parquet_smoke.py
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import pyarrow as pa

from app.repos.parquet.datasets import (
    begin_atomic_write,
    latest_snapshot,
    scan,
    write_schema_version,
    get_parquet_root,
)

def now_run_id() -> str:
    # 20250912T093000Z
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

def cmd_write(args):
    run_id = args.run_id or now_run_id()
    rows = int(args.rows)
    table = args.table

    # Minimal synthetic rows for scores/universe/etc.
    data = {
        "symbol": [f"SYM{i:03d}" for i in range(rows)],
        "name": [f"Name {i}" for i in range(rows)],
        "sector": ["Energy"] * rows,
        "last": [100.0 + i for i in range(rows)],
        "change_pct": [0.1 * i for i in range(rows)],
        "score": [50 + (i % 50) for i in range(rows)],
        "strength": ["Moderate"] * rows,
        "run_id": [run_id] * rows,
        "as_of": [datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")] * rows,
    }
    tab = pa.table(data)

    # Ensure schema version exists
    write_schema_version(table, 1)

    w = begin_atomic_write(table, run_id)
    w.write_df(tab)
    w.commit()
    print(f"✓ wrote {rows} rows to {table}/run_id={run_id} at {get_parquet_root()}")

def cmd_read(args):
    table = args.table
    rid = args.run_id or latest_snapshot(table)
    if not rid:
        print("(no snapshot)")
        return
    tab = scan(table, run_id=rid)
    print(f"latest={rid}, rows={tab.num_rows}, cols={tab.num_columns}")
    # show few rows
    print(tab.slice(0, min(5, tab.num_rows)))

def main():
    p = argparse.ArgumentParser("parquet-smoke")
    sub = p.add_subparsers(dest="cmd", required=True)

    w = sub.add_parser("write", help="Write a tiny synthetic snapshot")
    w.add_argument("--table", required=True, choices=["universe", "prices", "indicators", "scores"])
    w.add_argument("--rows", default="5")
    w.add_argument("--run_id")
    w.set_defaults(func=cmd_write)

    r = sub.add_parser("read", help="Read latest snapshot")
    r.add_argument("--table", required=True, choices=["universe", "prices", "indicators", "scores"])
    r.add_argument("--run_id")
    r.set_defaults(func=cmd_read)

    args = p.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
