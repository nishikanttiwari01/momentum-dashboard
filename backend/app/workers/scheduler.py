# backend/app/workers/scheduler.py
from __future__ import annotations

"""
Simple in-process scheduler for periodic scans.
- Uses APScheduler's BackgroundScheduler (daemon thread).
- Coalesces missed runs to avoid backlog & ensures single-instance execution.
- Triggers the *same* service used by POST /scan to keep behavior consistent.
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any
import uuid
import logging
import time  # <-- added

from apscheduler.schedulers.background import BackgroundScheduler

from app.core import config
from app.core.db import get_session
from app.services.screening_service import run_screening
from app.workers.jobs import post_scan_jobs  # <-- added import

log = logging.getLogger(__name__)
_scheduler: Optional[BackgroundScheduler] = None


def _now_key() -> str:
    """Generate a stable idempotency key for each scheduled run."""
    # Example: "sched-2025-09-14T01:30:00Z-<uuid4>"
    t = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return f"sched-{t}-{uuid.uuid4().hex[:8]}"


def _run_once(universe: Optional[str]) -> None:
    """
    Execute one scheduled scan.
    - Opens a DB session via the existing dependency generator.
    - Calls the same service used by /scan, preserving Phase-9 semantics (empty snapshot).
    - Softly passes 'universe' in payload (Phase-10-ready, non-breaking).
    """
    start_ts = time.perf_counter()
    log.info("scheduled scan starting", extra={"universe": universe or "default"})

    # Acquire a SQLAlchemy session from the existing dependency
    gen = get_session()            # generator that yields a Session and closes in finally
    s = next(gen)                  # borrow a session from the dependency
    try:
        payload: Dict[str, Any] = {}
        if universe:
            payload["universe"] = universe  # accepted and soft-validated by the service (Phase-10)
        # Idempotency key ensures replay safety in jobs_repo (same semantics as /scan)
        key = _now_key()
        result, created = run_screening(session=s, key=key, payload=payload)
        log.info(
            "scheduled scan completed",
            extra={
                "run_id": result.run_id,
                "was_created": created,  # renamed from 'created'
                "status": result.status,
                "universe": universe or "default",
            },
        )

        # ---- NEW: run post-scan side effects (alerts, etc.) ----
        try:
            post_scan_jobs(result.run_id)
        except Exception as e:
            log.exception("post-scan jobs failed for run_id=%s: %s", result.run_id, e)
        # ---------------------------------------------------------

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
    log.info(
        "scheduler: started (every %s min) universe=%s",
        interval,
        sched_universe or "<default>",
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
