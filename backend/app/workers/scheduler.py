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
import time
from pathlib import Path  # <-- added

from apscheduler.schedulers.background import BackgroundScheduler

from app.core import config
from app.core.db import get_session
from app.services.screening_service import run_screening
from app.workers.jobs import post_scan_jobs
from app.repos.parquet import datasets  # <-- added (for root + target hint)

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

    # ---- TRUTH LOGS: where will intraday write land (hint) ----
    try:
        root = datasets.get_parquet_root().resolve()  # writer default is ./parquet unless PARQUET_ROOT is set
        date_utc = datetime.now(timezone.utc).date().isoformat()  # run_screening uses UTC for intraday date
        log.info(
            "scheduler_planned_intraday",
            extra={
                "universe": universe or "default",
                "parquet_root": str(root),
                "date_utc": date_utc,
                "target_hint": f"{root}/scores/intraday/date={date_utc}/run_id=<to-be-assigned>",
            },
        )
    except Exception:
        pass

    log.info("scheduled scan starting", extra={"universe": universe or "default"})

    # Acquire a SQLAlchemy session from the existing dependency
    gen = get_session()
    s = next(gen)
    try:
        payload: Dict[str, Any] = {}
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
