#!/usr/bin/env python3
import csv
import json
import time
from pathlib import Path
from typing import Iterable, Dict

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE = "http://localhost:8000/api/v1/instruments/{sym}/detail"
CSV_PATH = Path("D:\\WORK\\NEW_STOCK_DASHBOARD\\momentum-dashboard\\backend\\app\\assets\\presets\\ALL.csv")
OUT_NDJSON = Path("D:\\all_instruments_detail.ndjson")
FAIL_CSV = Path("failures.csv")

TIMEOUT = 20
PAUSE_SECS = 0.10         # be gentle on the API
RETRY_TOTAL = 5
RETRY_BACKOFF = 0.5       # 0.5, 1.0, 2.0, ... seconds

def load_symbols(csv_path: Path) -> list[str]:
    with csv_path.open(newline="", encoding="utf-8") as f:
        # try header first
        peek = f.read(1024); f.seek(0)
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
        if not r: continue
        s = r[idx].strip()
        if s: syms.append(s)
    return syms

def existing_symbols_from_ndjson(path: Path) -> set[str]:
    done = set()
    if not path.exists():
        return done
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                obj = json.loads(line)
                # stored as {"symbol": "...", "data": {...}}
                done.add(obj.get("symbol"))
            except Exception:
                # If a partial/corrupted line occurs, ignore and continue
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

def main():
    symbols = load_symbols(CSV_PATH)
    if not symbols:
        print("No symbols found in ALL.csv")
        return

    already = existing_symbols_from_ndjson(OUT_NDJSON)
    todo = [s for s in symbols if s not in already]
    print(f"Loaded {len(symbols)} symbols; {len(already)} already saved; {len(todo)} to fetch…")

    sess = make_session()
    failures: list[str] = []

    for i, sym in enumerate(todo, 1):
        data = fetch_detail(sess, sym)
        if data is not None:
            write_ndjson(OUT_NDJSON, sym, data)
        else:
            failures.append(sym)

        # progress every 50
        if i % 50 == 0:
            print(f"…fetched {i}/{len(todo)}")

        time.sleep(PAUSE_SECS)

    if failures:
        with FAIL_CSV.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["symbol"])
            for s in failures:
                w.writerow([s])
        print(f"Done with {len(failures)} failures → {FAIL_CSV.resolve()}")
    else:
        print("Done with 0 failures.")

    print(f"NDJSON written to: {OUT_NDJSON.resolve()}")
    print("You can convert NDJSON to one big JSON dict later if needed.")

if __name__ == "__main__":
    main()
