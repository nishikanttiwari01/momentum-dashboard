#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import time
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE = "http://localhost:8000/api/v1/instruments/{sym}/detail"
CSV_PATH = Path(r"D:\WORK\NEW_STOCK_DASHBOARD\momentum-dashboard\backend\app\assets\presets\ALL.csv")
DEFAULT_OUT_NDJSON = Path(r"D:\WORK\NEW_STOCK_DASHBOARD\output\all_instruments_detail.ndjson")
DEFAULT_FAIL_CSV = Path(r"D:\WORK\NEW_STOCK_DASHBOARD\output\error\failures.csv")

TIMEOUT = 20
PAUSE_SECS = 0.10         # be gentle on the API
RETRY_TOTAL = 5
RETRY_BACKOFF = 0.5       # 0.5, 1.0, 2.0, ... seconds


def _timestamp_label(as_of: Optional[date] = None, ts: Optional[datetime] = None) -> str:
    if as_of is not None:
        return as_of.strftime("%Y%m%d")
    if ts is None:
        ts = datetime.now()
    return ts.strftime("%Y%m%d_%H%M%S")


def _timestamped_path(path: Path, label: str) -> Path:
    return path.with_name(f"{path.stem}_{label}{path.suffix}")


def load_symbols(csv_path: Path) -> list[str]:
    with csv_path.open(newline="", encoding="utf-8") as f:
        peek = f.read(1024)
        f.seek(0)
        reader = csv.reader(f)
        rows = list(reader)
    if not rows:
        return []
    header = [h.strip().lower() for h in rows[0]]
    if "symbol" in header:
        idx = header.index("symbol")
        data = rows[1:]
    else:
        idx = 0
        data = rows
    syms = []
    for r in data:
        if not r:
            continue
        s = r[idx].strip()
        if s:
            syms.append(s)
    return syms


def existing_symbols_from_ndjson(path: Path) -> set[str]:
    done: set[str] = set()
    if not path.exists():
        return done
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                done.add(obj.get("symbol"))
            except Exception:
                continue
    return done


def make_session() -> requests.Session:
    sess = requests.Session()
    retry = Retry(
        total=RETRY_TOTAL,
        connect=RETRY_TOTAL,
        read=RETRY_TOTAL,
        status=RETRY_TOTAL,
        backoff_factor=RETRY_BACKOFF,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    sess.mount("http://", adapter)
    sess.mount("https://", adapter)
    sess.headers.update({"Connection": "keep-alive"})
    return sess


def fetch_detail(sess: requests.Session, symbol: str) -> Dict | None:
    url = BASE.format(sym=symbol)
    try:
        resp = sess.get(url, timeout=TIMEOUT)
        if resp.status_code != 200:
            raise requests.HTTPError(f"HTTP {resp.status_code} for {symbol}")
        return resp.json()
    except Exception as e:
        print(f"[WARN] {symbol}: {e}")
        return None


def write_ndjson(path: Path, symbol: str, data: Dict) -> None:
    rec = {"symbol": symbol, "data": data}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False))
        f.write("\n")


def run_fetch_details(
    *,
    csv_path: Path = CSV_PATH,
    base_output: Path = DEFAULT_OUT_NDJSON,
    base_failures: Path = DEFAULT_FAIL_CSV,
    as_of: Optional[date] = None,
    timestamp: Optional[datetime] = None,
) -> Path:
    label = _timestamp_label(as_of=as_of, ts=timestamp)
    output_path = _timestamped_path(base_output, label)
    failures_path = _timestamped_path(base_failures, label)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    failures_path.parent.mkdir(parents=True, exist_ok=True)

    symbols = load_symbols(csv_path)
    if not symbols:
        print("No symbols found in ALL.csv")
        return output_path

    already = existing_symbols_from_ndjson(output_path)
    todo = [s for s in symbols if s not in already]
    print(
        f"Loaded {len(symbols)} symbols; {len(already)} already saved; {len(todo)} to fetch"
    )

    sess = make_session()
    failures: list[str] = []

    for i, sym in enumerate(todo, 1):
        data = fetch_detail(sess, sym)
        if data is not None:
            write_ndjson(output_path, sym, data)
        else:
            failures.append(sym)

        if i % 50 == 0:
            print(f"fetched {i}/{len(todo)}")

        time.sleep(PAUSE_SECS)

    if failures:
        with failures_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["symbol"])
            for s in failures:
                w.writerow([s])
        print(f"Done with {len(failures)} failures -> {failures_path.resolve()}")
    else:
        print("Done with 0 failures.")

    print(f"NDJSON written to: {output_path.resolve()}")
    return output_path


def main() -> None:
    run_fetch_details()


if __name__ == "__main__":
    main()
