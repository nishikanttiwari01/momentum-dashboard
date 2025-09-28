#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---- CONFIG ----
BASE_URL = "http://localhost:8000/api/v1/screener"
SORT = "score.desc,last.desc"
PER_PAGE = 500
START_PAGE = 0                # <-- always start at page 0
MAX_PAGES = 10000
TIMEOUT = 20
DEFAULT_OUT_NDJSON = Path(r"D:\WORK\NEW_STOCK_DASHBOARD\output\screener_all.ndjson")
DEFAULT_FAIL_CSV = Path(r"D:\WORK\NEW_STOCK_DASHBOARD\output\error\screener_failed_pages.csv")

PAUSE_SECS = 0.10
RETRY_TOTAL = 5
RETRY_BACKOFF = 0.5


def _timestamp_label(as_of: Optional[date] = None, ts: Optional[datetime] = None) -> str:
    if as_of is not None:
        return as_of.strftime("%Y%m%d")
    if ts is None:
        ts = datetime.now()
    return ts.strftime("%Y%m%d_%H%M%S")


def _timestamped_path(path: Path, label: str) -> Path:
    return path.with_name(f"{path.stem}_{label}{path.suffix}")


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


def write_records_ndjson(path: Path, records: Iterable[Dict[str, Any]]) -> None:
    with path.open("a", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False))
            f.write("\n")


def extract_rows(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("items", "data", "results", "rows"):
            if key in payload and isinstance(payload[key], list):
                return [x for x in payload[key] if isinstance(x, dict)]
    return []


def has_more(payload: Any, rows_len: int, per_page: int, page: int) -> bool:
    if isinstance(payload, dict):
        for k in ("total_pages", "pages"):
            v = payload.get(k)
            if isinstance(v, int) and v > 0:
                return page + 1 < v
        for k in ("has_more", "hasMore"):
            v = payload.get(k)
            if isinstance(v, bool):
                return v
        nxt = payload.get("next")
        if isinstance(nxt, (str, dict)) and nxt:
            return True
    return rows_len == per_page


def fetch_page(sess: requests.Session, page: int, per_page: int) -> Any:
    params = {"sort": SORT, "page": page, "per_page": per_page}
    resp = sess.get(BASE_URL, params=params, timeout=TIMEOUT)
    if resp.status_code != 200:
        raise requests.HTTPError(f"HTTP {resp.status_code} for page {page}")
    return resp.json()


def run_fetch_screener_pages(
    *,
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

    current_page = START_PAGE
    sess = make_session()
    failures: List[int] = []
    total_rows = 0

    print(f"Fetching pages starting at page={current_page}, per_page={PER_PAGE}")

    for _ in range(MAX_PAGES):
        try:
            payload = fetch_page(sess, current_page, PER_PAGE)
        except Exception as e:
            print(f"[WARN] page {current_page}: {e}")
            failures.append(current_page)
            current_page += 1
            time.sleep(PAUSE_SECS)
            continue

        rows = extract_rows(payload)
        if not rows:
            print(f"Stopping: no rows at page {current_page}")
            break

        write_records_ndjson(output_path, rows)
        total_rows += len(rows)
        print(f"Page {current_page}: wrote {len(rows)} rows (total {total_rows})")

        if not has_more(payload, len(rows), PER_PAGE, current_page):
            print("No more pages indicated by API/heuristics.")
            break

        current_page += 1
        time.sleep(PAUSE_SECS)

    if failures:
        with failures_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["page"])
            w.writerows([[p] for p in failures])
        print(f"Completed with {len(failures)} failed pages -> {failures_path.resolve()}")
    else:
        print("Completed with 0 failed pages.")

    print(f"NDJSON written to: {output_path.resolve()}")
    return output_path


def main() -> None:
    run_fetch_screener_pages()


if __name__ == "__main__":
    main()
