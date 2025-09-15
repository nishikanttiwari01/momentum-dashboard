# backend/app/cli/backfill.py
from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from datetime import date, timedelta, datetime
from typing import Iterable, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

API = os.getenv("MD_API", "http://127.0.0.1:8000")  # avoid localhost DNS on Windows


def _trading_days(start: date, end: date) -> Iterable[date]:
    d = start
    while d <= end:
        if d.weekday() < 5:  # Mon–Fri; swap in an exchange calendar if you have one
            yield d
        d += timedelta(days=1)


@dataclass
class BackfillConfig:
    months_back: int = 12
    sleep_between_sec: float = 0.5     # be nice to the API
    timeout_connect: float = 5.0
    timeout_read: float = 180.0
    max_retries: int = 4               # per request
    backoff_factor: float = 0.8
    start: Optional[date] = None       # override window
    end: Optional[date] = None


def _session(cfg: BackfillConfig) -> requests.Session:
    sess = requests.Session()
    # Retries on connection resets/EOFs/5xx; idempotent POST because we use Idempotency-Key
    retry = Retry(
        total=cfg.max_retries,
        connect=cfg.max_retries,
        read=cfg.max_retries,
        backoff_factor=cfg.backoff_factor,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["POST", "GET"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=2, pool_maxsize=2)
    sess.mount("http://", adapter)
    sess.mount("https://", adapter)
    # Some Windows stacks behave better if we disable keep-alive
    sess.headers.update({"Connection": "close", "Accept": "application/json"})
    return sess


def _post_scan(session: requests.Session, d: Optional[date], cfg: BackfillConfig) -> dict:
    key = f"BF_{(d or date.today()).isoformat()}"
    payload = {"as_of": d.isoformat()} if d else {}
    r = session.post(
        f"{API}/api/v1/scan",
        json=payload,
        headers={"Idempotency-Key": key, "Content-Type": "application/json"},
        timeout=(cfg.timeout_connect, cfg.timeout_read),
    )
    if r.status_code not in (200, 201):
        # Don’t crash the whole run; bubble up a concise error for this day
        raise RuntimeError(f"{d}: HTTP {r.status_code} {r.text[:200]}")
    return r.json()


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    cfg = BackfillConfig()

    # Optional CLI: backfill.py [YYYY-MM-DD] [YYYY-MM-DD]
    if len(argv) >= 1:
        cfg.start = date.fromisoformat(argv[0])
    if len(argv) >= 2:
        cfg.end = date.fromisoformat(argv[1])

    today = date.today()
    start = cfg.start or (today - timedelta(days=int(cfg.months_back * 365 / 12) + 30))
    end = cfg.end or today

    sess = _session(cfg)
    failures: list[str] = []

    print(f"Backfill window: {start} → {end}  (API={API})")
    for d in _trading_days(start, end):
        try:
            print("scan", d)
            _post_scan(sess, d, cfg)
        except Exception as e:
            # Record and continue; we’ll print a retry command at the end
            print(f"!! failed {d}: {e}", file=sys.stderr)
            failures.append(f"{d}")
        time.sleep(cfg.sleep_between_sec)

    if failures:
        print("\nSome days failed:")
        for x in failures:
            print("  ", x)
        print("\nRetry one day:")
        print(f"  python -m app.cli.backfill {failures[0]}")
        return 2

    print("\nBackfill complete ✔")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
