# backend/app/cli/backfill.py
from __future__ import annotations

import os
import sys
import time
import logging
import shutil
from dataclasses import dataclass
from datetime import date, timedelta, datetime, timezone  # <-- added datetime, timezone
from typing import Iterable, Optional, Tuple, Dict, Any, Callable  # <-- added Callable
import csv  # <-- added
import math
from uuid import uuid4

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from pathlib import Path as _Path

try:
    import pyarrow.dataset as _pa_ds
    import pyarrow.compute as _pa_compute
except Exception:  # pragma: no cover
    _pa_ds = None  # type: ignore
    _pa_compute = None  # type: ignore

from app.services.alerts import route_event as _route_alert_event
from app.alerts.types import Mode as _RouteMode

from backend.util import run_fetch_details, run_fetch_screener_pages
from app.notifs.email_digest import send_backfill_digest_if_enabled

# === NEW (alerts orchestrator integration) ====================================
try:
    from app.core import config as _cfg_mod
    from app.core.db import get_session as _get_session
    from app.alerts.types import Mode as _AlertMode
    from app.alerts import orchestrator as _alerts_orchestrator
    _ALERTS_OK = True
except Exception:
    _ALERTS_OK = False
# =============================================================================

API = os.getenv("MD_API", "http://127.0.0.1:8000")

log = logging.getLogger(__name__)

DEFAULT_INTRADAY_RETENTION_DAYS = 15

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
    base_key = f"BF_{(d or date.today()).isoformat()}"
    attempt_tag = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    key = f"{base_key}_{attempt_tag}_{uuid4().hex[:8]}"
    payload: Dict[str, Any] = {"as_of": d.isoformat()} if d else {}
    log.info(
        "scan_request",
        extra={
            "as_of": payload.get("as_of"),
            "idempotency_key": key,
            "api": API,
            "idempotency_base": base_key,
        },
    )
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

def _prune_intraday_history(retention_days: int, *, reference_date: date | None = None) -> None:
    """
    Remove intraday partitions older than the retention window.
    """
    try:
        days = int(retention_days)
    except (TypeError, ValueError):
        log.warning("intraday_retention_invalid", extra={"value": retention_days})
        return
    if days < 1:
        log.warning("intraday_retention_out_of_range", extra={"value": days})
        return

    base = _parquet_root_abs() / "scores" / "intraday"
    if not base.exists():
        return

    ref = reference_date or date.today()
    cutoff = ref - timedelta(days=days)

    for child in list(base.iterdir()):
        if not child.is_dir():
            continue
        folder_name = child.name
        date_str: Optional[str] = None
        for prefix in ("date=", "as_of="):
            if folder_name.startswith(prefix):
                date_str = folder_name[len(prefix):]
                break
        if not date_str:
            continue
        try:
            partition_date = date.fromisoformat(date_str)
        except ValueError:
            continue
        if partition_date < cutoff:
            try:
                shutil.rmtree(child)
                log.info(
                    "intraday_history_pruned",
                    extra={
                        "path": str(child),
                        "partition_date": partition_date.isoformat(),
                        "cutoff": cutoff.isoformat(),
                        "retention_days": days,
                    },
                )
            except Exception:
                log.exception(
                    "intraday_history_prune_failed",
                    extra={
                        "path": str(child),
                        "partition_date": partition_date.isoformat(),
                        "retention_days": days,
                    },
                )


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


# --- Housekeeping config helpers --------------------------------------------
def _intraday_retention_days() -> int:
    value = DEFAULT_INTRADAY_RETENTION_DAYS
    try:
        settings = _cfg_mod.load()
        runtime_cfg = getattr(settings, "backfill_runtime", None)
        candidate: Any = None
        if isinstance(runtime_cfg, dict):
            candidate = runtime_cfg.get("intraday_retention_days")
        elif runtime_cfg is not None:
            candidate = getattr(runtime_cfg, "intraday_retention_days", None)
        if candidate is None:
            return value
        try:
            days = int(candidate)
        except (TypeError, ValueError):
            log.warning("intraday_retention_invalid", extra={"value": candidate})
            return value
        if days < 1:
            log.warning("intraday_retention_out_of_range", extra={"value": days})
            return value
        return days
    except Exception as e:
        log.warning("intraday_retention_resolve_failed", extra={"error": str(e)})
        return value


# === NEW: Alerts helpers (self-contained, non-invasive) =======================

def _resolve_alerts_cfg_dict() -> Dict[str, Any] | None:
    """
    Return the 'alerts' config as a plain dict, or None if not configured.
    """
    if not _ALERTS_OK:
        return None
    try:
        cfg = _cfg_mod.load()
        alerts = getattr(cfg, "alerts", None)
        if alerts is None:
            return None
        if hasattr(alerts, "model_dump"):
            d = alerts.model_dump()
        elif hasattr(alerts, "dict"):
            d = alerts.dict()
        elif isinstance(alerts, dict):
            d = alerts
        else:
            d = dict(alerts.__dict__)
        return d.get("alerts", d)
    except Exception as e:
        log.warning("alerts_cfg_load_failed(backfill)", extra={"error": str(e)})
        return None


def _sanitize_metric_value(value: Any) -> Any:
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, list):
        return [_sanitize_metric_value(item) for item in value]
    if isinstance(value, dict):
        return {k: _sanitize_metric_value(v) for k, v in value.items()}
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()  # datetime/date
        except Exception:
            return value
    return value


def _safe_float(value: Any) -> Optional[float]:
    if value in (None, "", "None"):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _sanitize_for_json(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (list, tuple, set)):
        return [_sanitize_for_json(item) for item in value]
    if isinstance(value, dict):
        return {key: _sanitize_for_json(val) for key, val in value.items()}
    return value


def _load_metrics_from_daily_scores(as_of: date) -> tuple[list[str], Dict[str, Dict[str, Any]]]:
    if _pa_ds is None or _pa_compute is None:
        log.warning(
            "alerts_metrics_pyarrow_missing",
            extra={"date": as_of.isoformat()},
        )
        return [], {}

    root = _parquet_root_abs() / "scores" / "daily" / f"as_of={as_of.isoformat()}"
    if not root.exists():
        log.info(
            "alerts_metrics_parquet_missing",
            extra={"date": as_of.isoformat(), "path": str(root)},
        )
        return [], {}

    run_dirs = sorted([p for p in root.glob("run_id=*") if p.is_dir()])
    dataset_source = str(run_dirs[-1] if run_dirs else root)

    try:
        dataset = _pa_ds.dataset(
            dataset_source,
            format="parquet",
            partitioning="hive",
            exclude_invalid_files=True,
        )
        table = dataset.to_table()
    except Exception as exc:
        log.warning(
            "alerts_metrics_parquet_read_failed",
            extra={"date": as_of.isoformat(), "path": str(root), "error": str(exc)},
        )
        return [], {}

    if table.num_rows == 0:
        log.info(
            "alerts_metrics_parquet_empty",
            extra={"date": as_of.isoformat(), "path": str(root)},
        )
        return [], {}

    if "buy_flag" not in table.column_names:
        log.info(
            "alerts_metrics_parquet_no_buy_flag",
            extra={"date": as_of.isoformat(), "path": str(root)},
        )
        return [], {}

    try:
        mask = _pa_compute.equal(table["buy_flag"], True)
        filtered = table.filter(mask)
    except Exception as exc:
        log.warning(
            "alerts_metrics_parquet_filter_failed",
            extra={"date": as_of.isoformat(), "error": str(exc)},
        )
        return [], {}

    if filtered.num_rows == 0:
        log.info(
            "alerts_metrics_parquet_no_buy_candidates",
            extra={"date": as_of.isoformat()},
        )
        return [], {}

    metrics: Dict[str, Dict[str, Any]] = {}
    symbols: list[str] = []

    for record in filtered.to_pylist():
        sym_raw = record.get("symbol")
        symbol = str(sym_raw).strip().upper() if sym_raw else ""
        if not symbol:
            continue
        if symbol in metrics:
            continue
        symbol_metrics: Dict[str, Any] = {}
        for key, value in record.items():
            lowered = str(key).strip().lower()
            symbol_metrics[lowered] = _sanitize_metric_value(value)
        metrics[symbol] = symbol_metrics
        symbols.append(symbol)

    log.info(
        "alerts_metrics_parquet_loaded",
        extra={"date": as_of.isoformat(), "symbols": len(symbols)},
    )
    return symbols, metrics


def _read_symbols_and_metrics_from_details_csv(as_of: date) -> tuple[list[str], Dict[str, Dict[str, Any]]]:
    """
    Preferred path: load BUY=Yes rows from the daily scores parquet snapshot.
    Falls back to the legacy detail-export reader if parquet is unavailable.
    """
    symbols, metrics = _load_metrics_from_daily_scores(as_of)
    if symbols:
        return symbols, metrics

    # Legacy fallback (NDJSON/CSV export) for environments where parquet is unavailable.
    fallback_symbols: list[str] = []
    fallback_metrics: Dict[str, Dict[str, Any]] = {}

    try:
        csv_path = run_fetch_details(as_of=as_of)  # idempotent
        p = _Path(str(csv_path))
        if not p.exists():
            return fallback_symbols, fallback_metrics

        with p.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = [fn for fn in (reader.fieldnames or [])]
            lower_map = {fn.lower(): fn for fn in fieldnames}
            sym_col = lower_map.get("symbol") or lower_map.get("sym") or lower_map.get("ticker")
            if not sym_col:
                return fallback_symbols, fallback_metrics

            for row in reader:
                sym = (row.get(sym_col) or "").strip().upper()
                if not sym:
                    continue
                if sym not in fallback_metrics:
                    fallback_metrics[sym] = {}
                    fallback_symbols.append(sym)

                for k, v in row.items():
                    if k is None:
                        continue
                    key = k.strip().lower()
                    if isinstance(v, str):
                        vv = v.strip()
                        if vv == "":
                            fallback_metrics[sym][key] = None
                            continue
                        try:
                            if vv.isdigit() or (vv.startswith("-") and vv[1:].isdigit()):
                                fallback_metrics[sym][key] = int(vv)
                            else:
                                fallback_metrics[sym][key] = float(vv)
                        except ValueError:
                            fallback_metrics[sym][key] = vv
                    else:
                        fallback_metrics[sym][key] = v
    except Exception as e:
        log.warning("details_csv_read_failed", extra={"date": as_of.isoformat(), "error": str(e)})

    return fallback_symbols, fallback_metrics


def _make_metric_getter_from_metrics(metrics: Dict[str, Dict[str, Any]]) -> Callable[[str, str], Any]:
    """
    Returns metric_getter(symbol, name) using lowercase key lookup and a few aliases.
    """
    # conservative aliases to improve hit rate without guessing your schema
    aliases = {
        "score": ["score", "setup_score", "quality_score"],
        "relvol20": ["relvol20", "relvol_20", "rel_volume_20d"],
        "day_change_pct": ["day_change_pct", "pct_change", "change_pct"],
        "pivot_clear_pct": ["pivot_clear_pct", "bp_clear_pct", "breakout_clear_pct"],
        "rsi14": ["rsi14", "rsi_14"],
        "adx14": ["adx14", "adx_14"],
        "atr10_pct": ["atr10_pct", "atr10p", "atr10_pct_of_price"],
        "liquidity_rupees": ["liquidity_rupees", "turnover_rupees", "avg_turnover_20d"],
        "next_action_code": ["next_action_code", "next_action", "action_code"],
    }

    def getter(symbol: str, name: str):
        m = metrics.get(symbol.upper())
        if not m:
            return None
        key = (name or "").strip().lower()
        if key in m:
            return m[key]
        for alias in aliases.get(key, []):
            if alias in m:
                return m[alias]
        return None

    return getter


def _run_eod_alerts(trading_day: date) -> None:
    """
    After a daily snapshot is visible, load symbols/metrics from details CSV and
    invoke the alerts orchestrator in EOD mode. No-ops gracefully if anything
    required is missing.
    """
    if not _ALERTS_OK:
        log.info("alerts_skipped(backfill): package not available")
        return

    alerts_cfg = _resolve_alerts_cfg_dict()
    if not alerts_cfg:
        log.info("alerts_skipped(backfill): config not loaded")
        return

    symbols, metrics = _read_symbols_and_metrics_from_details_csv(trading_day)
    if not symbols:
        log.info("alerts_skipped(backfill): no symbols from details CSV", extra={"date": trading_day.isoformat()})
        return

    metric_getter = _make_metric_getter_from_metrics(metrics)

    # DB session / connection
    gen = _get_session()
    session = next(gen)
    try:
        try:
            conn = session.connection()
        except Exception:
            bind = session.get_bind()
            conn = bind.connect() if bind is not None else None
        if conn is None:
            log.warning("alerts_skipped(backfill): db connection unavailable")
            return

        now_utc = datetime.now(timezone.utc)
        routes_cfg = (alerts_cfg or {}).get("routes") or {}
        created_ids: list[int] = []

        if routes_cfg:
            for sym in symbols:
                row = metrics.get(sym.upper()) or {}
                if not row:
                    continue
                context_payload = _sanitize_for_json({
                    "symbol": sym,
                    "profile": row.get("buy_profile"),
                    "mode": row.get("buy_mode") or _RouteMode.EOD.value,
                    "run_id": row.get("run_id"),
                    "as_of": row.get("as_of") or trading_day.isoformat(),
                    "price": row.get("last"),
                    "score": row.get("score"),
                    "adx14": row.get("adx14"),
                    "relvol20": row.get("relvol20"),
                    "intraday_relvol": row.get("intraday_relvol"),
                    "atr_pct": row.get("atr_pct") or row.get("atr10_pct"),
                    "reasons_inline": row.get("buy_reasons_inline"),
                    "pass_count": row.get("buy_pass_count"),
                    "total_count": row.get("buy_total_count"),
                    "minutes_since_open": row.get("minutes_since_open"),
                    "above_vwap": row.get("above_vwap"),
                    "prev_day_high_clear": row.get("prev_day_high_clear"),
                    "liquidity": row.get("liquidity") or row.get("median_traded_value_20d"),
                    "buy_checks": row.get("buy_checks"),
                    "pivot": row.get("pivot_high_20") or row.get("pivot"),
                    "base_len_bars": row.get("base_len_bars"),
                })
                if context_payload.get("reasons_inline") and not context_payload.get("description"):
                    context_payload["description"] = context_payload["reasons_inline"]
                event_id = _route_alert_event(
                    session,
                    event_code="BUY_SIGNAL_EOD",
                    symbol=sym.upper(),
                    mode=_RouteMode.EOD,
                    trading_date=trading_day,
                    context=context_payload,
                    score_at_fire=_safe_float(row.get("score")),
                    next_action_code=str(row.get("next_action_code") or "").upper() or None,
                )
                if event_id:
                    created_ids.append(event_id)
        else:
            created_ids = _alerts_orchestrator.run(
                conn,
                alerts_cfg=alerts_cfg,
                symbols=symbols,
                mode=_AlertMode.EOD,
                trading_date=trading_day,
                now_utc=now_utc,
                metric_getter=metric_getter,
                run_ctx={"triggered_by": "STARTUP_CATCHUP"},
            )

        try:
            session.commit()
        except Exception:
            pass

        log.info(
            "alerts_eod_created",
            extra={"count": len(created_ids), "date": trading_day.isoformat()},
        )
    except Exception as e:
        log.exception("alerts_eod_failed", extra={"date": trading_day.isoformat(), "error": str(e)})
    finally:
        try:
            conn.close()
        except Exception:
            pass
        try:
            gen.close()
        except Exception:
            pass
# =============================================================================

# --- NEW: tiny helper to read the top-level news.enabled gate -----------------
def _news_enabled() -> bool:
    try:
        # Prefer the convenience helper if present
        if hasattr(_cfg_mod, "news_enabled"):
            return bool(_cfg_mod.news_enabled())
        # Fallback to direct Settings access
        return bool(_cfg_mod.load().news.enabled)
    except Exception as e:
        log.warning("news_enabled_resolve_failed", extra={"error": str(e)})
        # Preserve historical behavior (enabled) if config is unreadable
        return True
# -----------------------------------------------------------------------------


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
    retention_days = _intraday_retention_days()
    _prune_intraday_history(retention_days, reference_date=today)

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
                # === NEW: obey top-level news.enabled gate ===
                if not _news_enabled():
                    log.info("news_backfill_skipped(disabled)", extra={"date": d.isoformat()})
                else:
                    provider_cmd_env = (os.getenv("NEWS_PROVIDER_CMD") or "").strip()
                    provider_cmd = provider_cmd_env or None
                    log.info("news_backfill_provider_resolved", extra={"date": d.isoformat(), "provider_cmd": provider_cmd_env or "internal"})

                    from app.cli.news_pull import run_backfill as run_news_backfill  # local import

                    news_concurrency = 1
                    conc_env = (os.getenv("NEWS_CONCURRENCY") or "").strip()
                    log.info("conc_env= %s", conc_env)
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
                    log.info("shard_env= %s", shard_env)
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

            # === NEW: Fire EOD alerts after daily is visible (and details CSV is available) ===
            try:
                if _daily_partition_committed(d) or _daily_partition_has_parquet(d):
                    _run_eod_alerts(d)
            except Exception as e:
                log.exception("alerts_hook_failed(backfill)", extra={"date": d.isoformat(), "error": str(e)})

            if _daily_partition_has_parquet(d):
                if retention_days <= 0:
                    if d not in cleaned_intraday:
                        _delete_intraday_partition(d)
                        cleaned_intraday.add(d)
                else:
                    _prune_intraday_history(retention_days, reference_date=today)
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

    _prune_intraday_history(retention_days, reference_date=today)

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
