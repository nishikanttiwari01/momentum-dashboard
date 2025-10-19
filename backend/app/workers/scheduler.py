# backend/app/workers/scheduler.py
from __future__ import annotations

"""
Simple in-process scheduler for periodic scans.
- Uses APScheduler's BackgroundScheduler (daemon thread).
- Coalesces missed runs to avoid backlog & ensures single-instance execution.
- Triggers the *same* service used by POST /scan to keep behavior consistent.
"""

from datetime import datetime, timezone, timedelta, date, time as dtime
from typing import Optional, Dict, Any, Iterable, Callable
import uuid
import logging
import time
from pathlib import Path  # <-- added

from apscheduler.schedulers.background import BackgroundScheduler

from app.core import config
from app.core.db import get_session
from app.services.screening_service import run_screening
from app.workers.jobs import post_scan_jobs
from app.repos.parquet import datasets  # <-- added (for root + target hint)
from zoneinfo import ZoneInfo

# === NEW: alerts orchestrator integration (non-invasive) ===
try:
    from app.alerts.types import Mode as _AlertMode
    from app.alerts import orchestrator as _alerts_orchestrator
    _ALERTS_AVAILABLE = True
except Exception:
    _ALERTS_AVAILABLE = False

log = logging.getLogger(__name__)
_scheduler: Optional[BackgroundScheduler] = None


def _now_key() -> str:
    """Generate a stable idempotency key for each scheduled run."""
    # Example: "sched-2025-09-14T01:30:00Z-<uuid4>"
    t = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return f"sched-{t}-{uuid.uuid4().hex[:8]}"


def _current_trading_day(now: Optional[datetime] = None) -> date:
    dt = now or datetime.now(timezone.utc)
    d = dt.date()
    if d.weekday() >= 5:
        # Saturday (5) -> Friday, Sunday (6) -> Friday
        d -= timedelta(days=d.weekday() - 4)
    return d

def _now_in_trading_window(now_utc: Optional[datetime] = None) -> tuple[bool, Dict[str, Any]]:
    """
    Check whether 'now' (UTC) is inside the configured trading window.
    If no window is configured, return (True, meta) to preserve legacy behavior.
    """
    cfg = config.load()
    tw = getattr(cfg.scheduler, "trading_window", None)
    meta: Dict[str, Any] = {}

    if not tw:
        meta.update({"mode": "no_window_config"})
        return True, meta

    try:
        if hasattr(tw, "model_dump"):
            tw = tw.model_dump()
        elif hasattr(tw, "dict"):
            tw = tw.dict()
        if not isinstance(tw, dict):
            meta.update({"mode": "invalid_window_config", "value_type": type(tw).__name__})
            log.warning("trading_window_invalid_type", extra=meta)
            return True, meta

        tz_name = tw.get("tz", "Asia/Kolkata")
        start_str = tw.get("start", "09:15")
        end_str = tw.get("end", "15:30")
        days = tw.get("days", [0, 1, 2, 3, 4])  # Mon-Fri by default (Monday=0)

        tz = ZoneInfo(tz_name)
        now_utc = now_utc or datetime.now(timezone.utc)
        now_local = now_utc.astimezone(tz)

        # Parse HH:MM
        sh, sm = [int(x) for x in start_str.split(":")]
        eh, em = [int(x) for x in end_str.split(":")]
        start_t = dtime(hour=sh, minute=sm)
        end_t = dtime(hour=eh, minute=em)

        wd = now_local.weekday()  # Monday=0..Sunday=6
        within_day = wd in days
        within_clock = (start_t <= now_local.time() < end_t) if start_t <= end_t else (now_local.time() >= start_t or now_local.time() < end_t)  # handles overnight windows

        meta.update({
            "tz": tz_name,
            "weekday": wd,
            "days": days,
            "start": start_str,
            "end": end_str,
            "now_local": now_local.isoformat(),
            "within_day": within_day,
            "within_clock": within_clock,
        })
        return (within_day and within_clock), meta
    except Exception as e:
        # On any parsing/logic error, fail-open to preserve scanning (but log it).
        meta.update({"error": str(e), "mode": "fail_open"})
        log.warning("trading_window_check_failed", extra=meta)
        return True, meta


def _daily_partition_has_parquet(trading_day: date) -> bool:
    try:
        partition = datasets.get_parquet_root().resolve() / "scores" / "daily" / f"as_of={trading_day.isoformat()}"
    except Exception:
        return False
    if not partition.exists():
        return False
    try:
        next(partition.rglob("*.parquet"))
        return True
    except StopIteration:
        return False
    except Exception as exc:
        log.warning(
            "scheduler_daily_check_failed",
            extra={"date": trading_day.isoformat(), "error": str(exc)}
        )
        return False


# === NEW helpers for alerts wiring (safe, minimal) ============================

def _resolve_alerts_cfg_dict() -> Dict[str, Any] | None:
    """
    Try to get alerts config (dict under key 'alerts') from app.core.config.load().
    Robust to pydantic models / plain dicts. Returns None if not present.
    """
    try:
        cfg = config.load()
        alerts = getattr(cfg, "alerts", None)
        if alerts is None:
            return None
        # pydantic v2
        if hasattr(alerts, "model_dump"):
            d = alerts.model_dump()
        # pydantic v1
        elif hasattr(alerts, "dict"):
            d = alerts.dict()
        elif isinstance(alerts, dict):
            d = alerts
        else:
            # last resort: if cfg is dict-like
            d = dict(alerts.__dict__)
        # We expect top-level to BE the 'alerts' dict already (per your updated config.py)
        # If someone nested it, try to unwrap.
        return d.get("alerts", d)
    except Exception as e:
        log.warning("alerts_cfg_load_failed", extra={"error": str(e)})
        return None


def _guess_symbols_from_result(result) -> list[str]:
    """
    Best-effort ways to get the universe symbols from the screening result.
    We DO NOT hard-depend on any specific attribute. If we can't find symbols,
    we return [] and skip alerts gracefully.
    """
    # Common patterns in services: result.universe_symbols, result.symbols
    for attr in ("universe_symbols", "symbols"):
        syms = getattr(result, attr, None)
        if syms:
            try:
                return list(syms)
            except Exception:
                pass
    # As a last resort, try a snapshot-based hint (do not read parquet here).
    # Keep empty to avoid breaking if nothing is available.
    return []


def _make_metric_getter_for_intraday(result) -> Callable[[str, str], Any]:
    """
    Provide a metric_getter(symbol, name) for orchestrator that is safe even if the
    underlying source isn't available here. We only log and return None on misses.
    The real metric plumbing can be wired in the backfill/worker where the data loaders live.
    """
    # If the screening service exposes one (ideal), use it.
    mg = getattr(result, "metric_getter", None)
    if callable(mg):
        return mg

    # Fallback: a null getter that returns None (filters will fail -> no alerts).
    def _null_getter(symbol: str, name: str):
        return None
    return _null_getter


def _run_intraday_alerts(session, *, trading_day: date, result) -> None:
    """
    Non-invasive alerts trigger: only runs if alerts orchestrator & cfg are present,
    and we can obtain a non-empty symbol list. Otherwise, no-op.
    """
    if not _ALERTS_AVAILABLE:
        log.info("alerts_orchestrator_missing_skip")
        return

    alerts_cfg = _resolve_alerts_cfg_dict()
    if not alerts_cfg:
        log.info("alerts_cfg_missing_skip")
        return

    symbols = _guess_symbols_from_result(result)
    if not symbols:
        log.info("alerts_symbols_missing_skip", extra={"reason": "no_symbols_from_result"})
        return

    metric_getter = _make_metric_getter_for_intraday(result)

    now_utc = datetime.now(timezone.utc)
    try:
        conn = session.connection()
    except Exception:
        # If Session.connection() isn't available, fall back to bind.connect()
        bind = session.get_bind()
        conn = bind.connect() if bind is not None else None

    if conn is None:
        log.warning("alerts_conn_unavailable_skip")
        return

    try:
        created_ids = _alerts_orchestrator.run(
            conn,
            alerts_cfg=alerts_cfg,
            symbols=symbols,
            mode=_AlertMode.INTRADAY,          # scheduler runs inside trading window
            trading_date=trading_day,
            now_utc=now_utc,
            metric_getter=metric_getter,
            run_ctx={"triggered_by": "SCHEDULE"},
        )
        log.info("alerts_intraday_created", extra={"count": len(created_ids), "trading_date": trading_day.isoformat()})
    except Exception as e:
        log.exception("alerts_intraday_failed", extra={"error": str(e)})
    finally:
        try:
            conn.close()
        except Exception:
            pass
# =============================================================================


def _run_once(universe: Optional[str]) -> None:
    """
    Execute one scheduled scan.
    - Opens a DB session via the existing dependency generator.
    - Calls the same service used by /scan, preserving Phase-9 semantics (empty snapshot).
    - Softly passes 'universe' in payload (Phase-10-ready, non-breaking).
    """
    start_ts = time.perf_counter()
    trading_day = _current_trading_day()
    # ---- Trading window gate ----
    allowed, window_meta = _now_in_trading_window()
    if not allowed:
        log.info(
            "scheduled scan skipped: outside_trading_window",
            extra={
                "reason": "outside_trading_window",
                "universe": universe or "default",
                "trading_date": trading_day.isoformat(),
                **window_meta,
            },
        )
        return
    # ---- TRUTH LOGS: where will intraday write land (hint) ----
    try:
        root = datasets.get_parquet_root().resolve()  # writer default is ./parquet unless PARQUET_ROOT is set
        date_str = trading_day.isoformat()
        log.info(
            "scheduler_planned_intraday",
            extra={
                "universe": universe or "default",
                "parquet_root": str(root),
                "trading_date": date_str,
                "target_hint": f"{root}/scores/intraday/date={date_str}/run_id=<to-be-assigned>",
            },
        )
    except Exception:
        pass

    log.info(
        "scheduled scan starting trading_date=%s universe=%s",
        trading_day.isoformat(),
        universe or "default",
        extra={"universe": universe or "default", "trading_date": trading_day.isoformat()},
    )

    if _daily_partition_has_parquet(trading_day):
        log.info(
            "scheduled scan skipped trading_date=%s reason=%s universe=%s",
            trading_day.isoformat(),
            "daily_already_committed",
            universe or "default",
            extra={"reason": "daily_already_committed", "trading_date": trading_day.isoformat(), "universe": universe or "default"},
        )
        return

    # Acquire a SQLAlchemy session from the existing dependency
    gen = get_session()
    s = next(gen)
    try:
        payload: Dict[str, Any] = {"intraday_trading_date": trading_day.isoformat()}
        if universe:
            payload["universe"] = universe
        key = _now_key()

        # ---- call the same service as /scan ----
        result, created = run_screening(session=s, key=key, payload=payload)

        # Immediate truth log: run result and final snapshot path (if any)
        log.info(
            "scheduled_scan_completed",
            extra={
                "run_id": result.run_id,
                "was_created": created,
                "status": result.status,
                "universe": universe or "default",
                "snapshot_path": result.snapshot_path,  # set by run_screening to new layout paths
            },
        )

        # Best-effort listing of parquet parts at the target (helps confirm "actually wrote")
        try:
            if result.snapshot_path:
                tgt = Path(result.snapshot_path)
                if tgt.exists():
                    files = [p.name for p in tgt.glob("*.parquet")]
                    log.info("scheduler_postcommit_listing", extra={"target": str(tgt), "files": files})
                else:
                    # If daily was immutable no-op or path differs, at least show the parent date/as_of folder contents
                    parent = tgt.parent if tgt.parent else None
                    files = [p.name for p in parent.glob("*.parquet")] if (parent and parent.exists()) else []
                    log.warning(
                        "scheduler_postcommit_target_missing",
                        extra={"target": str(tgt), "parent": str(parent) if parent else None, "parent_files": files},
                    )
        except Exception as e:
            log.warning("scheduler_postcommit_listing_error", extra={"err": str(e)})

        # ---- post-scan side effects (alerts, etc.) ----
        try:
            post_scan_jobs(result.run_id)
        except Exception as e:
            log.exception("post-scan jobs failed for run_id=%s: %s", result.run_id, e)

        # ---- NEW: Intraday alerts after successful screening (non-invasive) ----
        try:
            _run_intraday_alerts(s, trading_day=trading_day, result=result)
        except Exception as e:
            log.exception("alerts hook failed", extra={"error": str(e)})

    except Exception as exc:
        log.exception("scheduled scan failed: %s", exc)
    finally:
        try:
            gen.close()
        except Exception:
            pass

        duration = time.perf_counter() - start_ts
        log.info(
            "scheduled scan finished",
            extra={
                "universe": universe or "default",
                "duration_sec": round(duration, 2),
            },
        )


def start_if_enabled() -> Optional[BackgroundScheduler]:
    """
    Start the scheduler if enabled in config.
    Returns the scheduler instance (or None if disabled) so callers can keep a handle.
    """
    global _scheduler
    if _scheduler is not None:
        return _scheduler  # already started

    cfg = config.load()
    if not cfg.scheduler.enabled:
        log.info("scheduler: disabled in config; not starting")
        return None

    # Resolve universe: prefer scheduler.universe; else fallback to screener.default_universe.
    sched_universe = (cfg.scheduler.universe or cfg.screener.default_universe or "").strip().upper() or None
    interval = int(cfg.scheduler.interval_minutes or 15)

    # Create a background (daemon) scheduler
    sch = BackgroundScheduler(daemon=True)

    # Add a single, coalesced job that fires every N minutes
    # - coalesce=True: if the app was paused, don't replay all missed fires
    # - max_instances=1: do not run two scans at once
    # - misfire_grace_time=900: allow up to 15 min delay tolerance
    sch.add_job(
        func=_run_once,
        trigger="interval",
        minutes=interval,
        args=[sched_universe],
        id="scan_every_n_minutes",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=900,
    )

    sch.start()
    _scheduler = sch

    # Truth log: scheduler config + resolved parquet root once.
    try:
        root = datasets.get_parquet_root().resolve()
        log.info(
            "scheduler_started",
            extra={
                "interval_min": interval,
                "universe": sched_universe or "<default>",
                "parquet_root": str(root),
            },
        )
    except Exception:
        log.info(
            "scheduler_started",
            extra={"interval_min": interval, "universe": sched_universe or "<default>"},
        )

    return _scheduler


def shutdown() -> None:
    """Shutdown the scheduler gracefully (idempotent)."""
    global _scheduler
    if _scheduler is None:
        return
    try:
        _scheduler.shutdown(wait=False)
    except Exception:
        pass
    finally:
        _scheduler = None
        log.info("scheduler: stopped")
