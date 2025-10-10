# backend/app/cli/backfill.py
from __future__ import annotations

import os
import sys
import time
import logging
import shutil
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable, Optional, Tuple, Dict, Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from pathlib import Path as _Path

from backend.util import run_fetch_details, run_fetch_screener_pages
from app.notifs.email_digest import send_backfill_digest_if_enabled


API = os.getenv("MD_API", "http://127.0.0.1:8000")

log = logging.getLogger(__name__)

def _setup_logging() -> None:
    if getattr(_setup_logging, "_configured", False):
        return
    handler = logging.StreamHandler(stream=sys.stdout)
    fmt = "%Y-%m-%d %H:%M:%S %(levelname)s [%(name)s] %(message)s"
    handler.setFormatter(logging.Formatter(fmt))
    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(handler)
        root.setLevel(logging.INFO)
    log.setLevel(logging.INFO)
    _setup_logging._configured = True  # type: ignore[attr-defined]


def _trading_days(start: date, end: date) -> Iterable[date]:
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


# ---------- Resolve parquet root exactly like datasets.py (if importable) ----------
_ROOT_LOGGED_ONCE = False
def _parquet_root_abs() -> _Path:
    try:
        # Prefer the same resolver as writers
        from app.repos.parquet.datasets import get_parquet_root  # type: ignore
        p = get_parquet_root()
        p = _Path(str(p)).resolve()
    except Exception:
        env_root = os.getenv("PARQUET_ROOT")
        if env_root:
            p = _Path(env_root).expanduser().resolve()
        else:
            # this file: backend/app/cli/backfill.py -> backend/
            p = _Path(__file__).resolve().parents[3] / "parquet"
            p = p.resolve()
    global _ROOT_LOGGED_ONCE
    if not _ROOT_LOGGED_ONCE:
        try:
            log.info("parquet_root_resolved(backfill)", extra={"parquet_root": str(p)})
        except Exception:
            pass
        _ROOT_LOGGED_ONCE = True
    return p

def _as_of_dir_exists(d: date) -> bool:
    """
    True if scores/daily/as_of=DATE already contains ANY data:
      - any run_id=* subfolder
      - OR any parquet files anywhere beneath
      - OR a _SUCCESS marker
    Daily partitions are immutable, so any presence means 'done'.
    """
    root = _parquet_root_abs() / "scores" / "daily" / f"as_of={d.isoformat()}"
    # If no as_of dir, clearly not done
    if not root.exists():
        return False
    try:
        # Check run_id subfolders quickly
        for child in root.iterdir():
            if child.is_dir() and child.name.startswith("run_id="):
                log.info("as_of_present(run_id)", extra={"date": d.isoformat(), "path": str(root)})
                return True
        # Check markers/files (robust against older layouts)
        if (root / "_SUCCESS").exists() or (root / "rowcount.txt").exists():
            log.info("as_of_present(marker)", extra={"date": d.isoformat(), "path": str(root)})
            return True
        # Any parquet files at any depth under as_of
        try:
            next(root.rglob("*.parquet"))
            log.info("as_of_present(parquet)", extra={"date": d.isoformat(), "path": str(root)})
            return True
        except StopIteration:
            return False
    except Exception as e:
        # If listing fails, be conservative and do not skip (avoid false positives)
        log.warning("as_of_check_failed", extra={"date": d.isoformat(), "path": str(root), "error": str(e)})
        return False


@dataclass
class BackfillConfig:
    months_back: int = 12
    sleep_between_sec: float = 0.5
    timeout_connect: float = 5.0
    timeout_read: float = 600.0  # allow long runs (10 min) to complete
    max_retries: int = 4
    backoff_factor: float = 0.8
    start: Optional[date] = None
    end: Optional[date] = None


def _session(cfg: BackfillConfig) -> requests.Session:
    sess = requests.Session()
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
    sess.headers.update({"Connection": "close", "Accept": "application/json"})
    return sess


def _post_scan(session: requests.Session, d: Optional[date], cfg: BackfillConfig) -> Tuple[int, Dict[str, Any]]:
    key = f"BF_{(d or date.today()).isoformat()}"
    payload: Dict[str, Any] = {"as_of": d.isoformat()} if d else {}
    log.info("scan_request", extra={"as_of": payload.get("as_of"), "idempotency_key": key, "api": API})
    r = session.post(
        f"{API}/api/v1/scan",
        json=payload,
        headers={"Idempotency-Key": key, "Content-Type": "application/json"},
        timeout=(cfg.timeout_connect, cfg.timeout_read),
    )
    log.info("scan_response", extra={"as_of": payload.get("as_of"), "status_code": r.status_code})

    if r.status_code not in (200, 201, 202):
        snippet = (r.text or "")[:400]
        log.error("scan_failed", extra={"as_of": payload.get("as_of"), "status_code": r.status_code, "body": snippet})
        raise RuntimeError(f"{d}: HTTP {r.status_code} {snippet}")

    try:
        data = r.json() or {}
    except Exception:
        data = {}

    counts = data.get("counts") or {}
    log.info(
        "scan_success",
        extra={
            "as_of": payload.get("as_of"),
            "status": ("created" if r.status_code == 201 else ("accepted" if r.status_code == 202 else "replayed")),
            "run_id": data.get("run_id"),
            "rows_written": counts.get("rows_written"),
            "snapshot_path": data.get("snapshot_path"),
        },
    )
    return r.status_code, data


def _should_export_utilities(status: int, payload: Dict[str, Any] | None) -> bool:
    if not payload:
        return False
    counts = payload.get('counts') or {}
    rows_value = counts.get('rows_written')
    try:
        rows_written = int(rows_value)
    except (TypeError, ValueError):
        rows_written = 0
    if rows_written > 0:
        return True
    snapshot_path = payload.get('snapshot_path')
    return bool(snapshot_path)

def _daily_partition_has_parquet(as_of: date) -> bool:
    partition_root = _parquet_root_abs() / "scores" / "daily" / f"as_of={as_of.isoformat()}"
    if not partition_root.exists():
        return False
    try:
        next(partition_root.rglob("*.parquet"))
        return True
    except StopIteration:
        return False
    except Exception as exc:
        log.warning(
            "daily_partition_check_failed",
            extra={"date": as_of.isoformat(), "path": str(partition_root), "error": str(exc)},
        )
        return False

# ---- commit visibility helpers (minimal, used before exports) ----------------
def _daily_partition_committed(as_of: date) -> bool:
    """Committed when a marker exists; avoids racing readers/exports."""
    root = _parquet_root_abs() / "scores" / "daily" / f"as_of={as_of.isoformat()}"
    return (root / "_SUCCESS").exists() or (root / "rowcount.txt").exists()

def _wait_for_daily_visible(as_of: date, max_wait_sec: int = 25, step_sec: float = 0.5) -> bool:
    """
    Wait until the daily snapshot is visible to readers.
    Prefer a commit marker; fall back to any *.parquet if the repo doesn't drop markers.
    """
    waited = 0.0
    while waited < max_wait_sec:
        if _daily_partition_committed(as_of) or _daily_partition_has_parquet(as_of):
            return True
        time.sleep(step_sec)
        waited += step_sec
    return _daily_partition_committed(as_of) or _daily_partition_has_parquet(as_of)
# -----------------------------------------------------------------------------

def _delete_intraday_partition(as_of: date) -> None:
    base = _parquet_root_abs() / "scores" / "intraday"
    candidates = [
        base / f"date={as_of.isoformat()}",
        base / f"as_of={as_of.isoformat()}",
    ]
    existing = [p for p in candidates if p.exists()]
    if not existing:
        log.info(
            "intraday_cleanup_missing",
            extra={"date": as_of.isoformat(), "paths_checked": [str(p) for p in candidates]},
        )
        return
    for intraday_root in existing:
        try:
            shutil.rmtree(intraday_root)
            log.info(
                "intraday_cleanup_done",
                extra={"date": as_of.isoformat(), "path": str(intraday_root)},
            )
        except Exception:
            log.exception(
                "intraday_cleanup_failed",
                extra={"date": as_of.isoformat(), "path": str(intraday_root)},
            )


def _trigger_util_exports(as_of: date) -> None:
    extra = {'date': as_of.isoformat()}
    try:
        details_path = run_fetch_details(as_of=as_of)
        log.info('export_details_success', extra={**extra, 'output': str(details_path)})
    except Exception:
        log.exception('export_details_failed', extra=extra)
    try:
        screener_path = run_fetch_screener_pages(as_of=as_of)
        log.info('export_screener_success', extra={**extra, 'output': str(screener_path)})
    except Exception:
        log.exception('export_screener_failed', extra=extra)



def main(argv: list[str] | None = None) -> int:
    _setup_logging()
    argv = argv or sys.argv[1:]
    cfg = BackfillConfig()

    try:
        if len(argv) >= 1 and argv[0]:
            cfg.start = date.fromisoformat(argv[0])
        if len(argv) >= 2 and argv[1]:
            cfg.end = date.fromisoformat(argv[1])
    except Exception as e:
        log.error("bad_date_args", extra={"argv": argv, "error": str(e)})
        print("Usage: python -m app.cli.backfill [YYYY-MM-DD] [YYYY-MM-DD]", file=sys.stderr)
        return 64

    today = date.today()
    yesterday = today - timedelta(days=1)

    start = cfg.start or (today - timedelta(days=int(cfg.months_back * 365 / 12) + 30))
    end = cfg.end or yesterday

    if end >= today:
        end = yesterday

    if start > end:
        log.warning("empty_backfill_window", extra={"start": start.isoformat(), "end": end.isoformat()})
        print("Empty backfill window; nothing to do.")
        return 0

    sess = _session(cfg)
    failures: list[str] = []
    total_rows = 0
    total_days = 0
    skipped_days = 0
    exported_dates: set[date] = set()
    cleaned_intraday: set[date] = set()

    log.info("backfill_window", extra={"start": start.isoformat(), "end": end.isoformat(), "api": API})
    print(f"Backfill window: {start} -> {end}  (API={API})")

    for d in _trading_days(start, end):
        total_days += 1
        if _as_of_dir_exists(d):
            skipped_days += 1
            log.info("day_skip_already_present", extra={"date": d.isoformat()})
            print("skip", d, "(already present)")
            continue

        try:
            print("scan", d)
            status, resp = _post_scan(sess, d, cfg)
            counts = (resp or {}).get("counts") or {}
            rows_value = counts.get("rows_written")
            try:
                rows_written = int(rows_value)
            except (TypeError, ValueError):
                rows_written = 0
            total_rows += rows_written
            log.info(
                "day_done",
                extra={
                    "date": d.isoformat(),
                    "status": ("created" if status == 201 else ("accepted" if status == 202 else "replayed")),
                    "rows_written": rows_value,
                },
            )

            # NEWS: run only when backfill actually wrote a new daily snapshot
            wrote_new = (status == 201) or (rows_written > 0)
            if wrote_new:
                provider_cmd_env = (os.getenv("NEWS_PROVIDER_CMD") or "").strip()
                provider_cmd = provider_cmd_env or None
                log.info("news_backfill_provider_resolved", extra={"date": d.isoformat(), "provider_cmd": provider_cmd_env or "internal"})

                from app.cli.news_pull import run_backfill as run_news_backfill  # local import

                news_concurrency = 1
                conc_env = (os.getenv("NEWS_CONCURRENCY") or "").strip()
                #conc_env = 20
                log.info(
                    "conc_env= %s", conc_env)
                if conc_env:
                    try:
                        news_concurrency = int(conc_env)
                    except ValueError:
                        log.warning(
                            "news_concurrency_invalid",
                            extra={"date": d.isoformat(), "value": conc_env},
                        )
                        news_concurrency = 1
                if news_concurrency < 1:
                    news_concurrency = 1

                shard_size: Optional[int] = None
                shard_env = (os.getenv("NEWS_SHARD_SIZE") or "").strip()
                #shard_env = 50
                log.info(
                    "shard_env= %s", shard_env)
                if shard_env:
                    try:
                        parsed = int(shard_env)
                        if parsed > 0:
                            shard_size = parsed
                    except ValueError:
                        log.warning(
                            "news_shard_size_invalid",
                            extra={"date": d.isoformat(), "value": shard_env},
                        )

                symbols_file_env = (os.getenv("NEWS_SYMBOLS_FILE") or "").strip()
                symbols_all_file = symbols_file_env or None

                log.info(
                    "news_backfill_begin",
                    extra={
                        "date": d.isoformat(),
                        "provider_cmd": provider_cmd_env or "internal",
                        "concurrency": news_concurrency,
                        "shard_size": (shard_size or 0),
                        "symbols_file": bool(symbols_all_file),
                    },
                )

                try:
                    run_news_backfill(
                        api_base=API,
                        trading_day=d,
                        provider_cmd=provider_cmd,
                        extra_env={},
                        symbols_all_file=symbols_all_file,
                        symbol_limit=None,
                        shard_size=shard_size,
                        concurrency=news_concurrency,
                    )
                    log.info(
                        "news_backfill_ok",
                        extra={
                            "date": d.isoformat(),
                            "mode": ("multi" if news_concurrency > 1 else "single"),
                        },
                    )
                except Exception:
                    log.exception(
                        "news_backfill_failed",
                        extra={
                            "date": d.isoformat(),
                            "provider_cmd": provider_cmd_env or "internal",
                        },
                    )


            if _should_export_utilities(status, resp) and d not in exported_dates:
                # Always wait briefly for daily snapshot visibility (commit marker or parquet)
                _wait_for_daily_visible(d)
                if _daily_partition_committed(d) or _daily_partition_has_parquet(d):
                    _trigger_util_exports(d)
                    exported_dates.add(d)
                else:
                    log.info("export_skipped_uncommitted", extra={"date": d.isoformat()})

            if d not in cleaned_intraday and _daily_partition_has_parquet(d):
                _delete_intraday_partition(d)
                cleaned_intraday.add(d)
            # after cleanup for that day...
            # ✉️ Send digest email for this day (best-effort, guarded by YAML flags)
            try:
                send_backfill_digest_if_enabled(d)
            except Exception:
                log.exception("backfill_email_digest_failed", extra={"date": d.isoformat()})

        except Exception as e:
            print(f"!! failed {d}: {e}", file=sys.stderr)
            log.exception("day_failed", extra={"date": d.isoformat()})
            failures.append(f"{d}")
        time.sleep(cfg.sleep_between_sec)

    log.info("backfill_done", extra={"days": total_days, "skipped": skipped_days, "failures": len(failures), "total_rows": total_rows})

    if failures:
        print("\nSome days failed:")
        for x in failures:
            print("  ", x)
        print("\nRetry one day:")
        print(f"  python -m app.cli.backfill {failures[0]}")
        return 2

    print("\nBackfill complete :)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
