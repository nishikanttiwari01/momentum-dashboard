# backend/app/workers/scheduler.py
from __future__ import annotations

"""
Simple in-process scheduler for periodic scans.
- Uses APScheduler's BackgroundScheduler (daemon thread).
- Coalesces missed runs to avoid backlog & ensures single-instance execution.
- Triggers the *same* service used by POST /scan to keep behavior consistent.
"""

from datetime import date, datetime, time as dtime, timedelta, timezone
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

# Lazy pyarrow for reading the just-written intraday scores parquet.
# Kept optional (scheduler still starts even if pyarrow is missing),
# but the intraday alert path cannot populate metrics without it and
# will skip loudly in that case.
try:
    import pyarrow.dataset as _pa_ds  # type: ignore
    import pyarrow.compute as _pa_compute  # type: ignore
except Exception:  # pragma: no cover
    _pa_ds = None  # type: ignore
    _pa_compute = None  # type: ignore

import math  # for NaN sanitisation in metric values

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


def _sanitize_metric_value(value: Any) -> Any:
    """Match the sanitisation used by backfill's EOD metric loader."""
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
            return value.isoformat()
        except Exception:
            return value
    return value


def _load_symbols_and_metrics_from_intraday_scores(
    snapshot_path: Optional[str],
) -> tuple[list[str], Dict[str, Dict[str, Any]]]:
    """
    Load (symbols, metrics) from the intraday scores parquet just written by run_screening.
    Mirrors backfill._load_metrics_from_daily_scores so the two alert paths behave the same way.

    Returns ([], {}) on any failure — callers should treat that as "no alerts this run"
    and log a loud reason, not silently skip.
    """
    if not snapshot_path:
        log.warning("alerts_intraday_snapshot_path_missing")
        return [], {}

    if _pa_ds is None or _pa_compute is None:
        log.warning(
            "alerts_intraday_pyarrow_missing",
            extra={"snapshot_path": snapshot_path},
        )
        return [], {}

    target = Path(snapshot_path)
    if not target.exists():
        log.warning(
            "alerts_intraday_snapshot_missing",
            extra={"snapshot_path": snapshot_path},
        )
        return [], {}

    try:
        dataset = _pa_ds.dataset(
            str(target),
            format="parquet",
            partitioning="hive",
            exclude_invalid_files=True,
        )
        table = dataset.to_table()
    except Exception as exc:
        log.warning(
            "alerts_intraday_parquet_read_failed",
            extra={"snapshot_path": snapshot_path, "error": str(exc)},
        )
        return [], {}

    if table.num_rows == 0:
        log.info(
            "alerts_intraday_parquet_empty",
            extra={"snapshot_path": snapshot_path},
        )
        return [], {}

    metrics: Dict[str, Dict[str, Any]] = {}
    symbols: list[str] = []
    for record in table.to_pylist():
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
        "alerts_intraday_metrics_loaded",
        extra={"snapshot_path": snapshot_path, "symbols": len(symbols)},
    )
    return symbols, metrics


# Aliases kept in lockstep with backfill._make_metric_getter_from_metrics so the
# intraday and EOD filter paths see the same metric surface.
_METRIC_ALIASES: Dict[str, list[str]] = {
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


def _make_metric_getter_from_metrics(
    metrics: Dict[str, Dict[str, Any]]
) -> Callable[[str, str], Any]:
    """Return metric_getter(symbol, name) with lowercase + alias lookup."""

    def getter(symbol: str, name: str):
        m = metrics.get((symbol or "").upper())
        if not m:
            return None
        key = (name or "").strip().lower()
        if key in m:
            return m[key]
        for alias in _METRIC_ALIASES.get(key, []):
            if alias in m:
                return m[alias]
        return None

    return getter


def _run_intraday_alerts(session, *, trading_day: date, result) -> None:
    """
    Trigger the alerts orchestrator in INTRADAY mode against the symbols/metrics
    from the just-written intraday scores parquet (result.snapshot_path).

    Previously this function used a null metric_getter as a "safe" fallback. That
    caused every filter in alerts/filters.py to return None -> filter failure, so
    the INTRADAY alert path silently produced zero events on every scheduled scan.
    The fix: load symbols + metrics from the run's own parquet snapshot and build
    a real metric_getter (same alias set as the EOD path in backfill.py).
    """
    if not _ALERTS_AVAILABLE:
        log.info("alerts_orchestrator_missing_skip")
        return

    alerts_cfg = _resolve_alerts_cfg_dict()
    if not alerts_cfg:
        log.info("alerts_cfg_missing_skip")
        return

    snapshot_path = getattr(result, "snapshot_path", None)
    symbols, metrics = _load_symbols_and_metrics_from_intraday_scores(snapshot_path)
    if not symbols:
        # _load_... has already logged the reason (pyarrow missing, snapshot missing,
        # empty table, etc.). We do NOT fall back to a null getter here any more.
        log.info(
            "alerts_intraday_skip_no_metrics",
            extra={"trading_date": trading_day.isoformat(), "snapshot_path": snapshot_path},
        )
        return

    metric_getter = _make_metric_getter_from_metrics(metrics)

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
        log.info(
            "alerts_intraday_created",
            extra={
                "count": len(created_ids),
                "trading_date": trading_day.isoformat(),
                "symbols_considered": len(symbols),
            },
        )
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

    # NOTE: there used to be an early-return here that skipped the scan whenever
    # today's *daily* (EOD) partition already existed. That was both redundant
    # (the trading-window gate above already prevents post-close scans) and
    # harmful: intraday scans write to scores/intraday/date=... — a different
    # partition from scores/daily/as_of=... — so the presence of a daily parquet
    # should never block intraday scans during market hours. It also caused the
    # only "live" alert path to fall silent as soon as any daily partition
    # appeared (including stale files from a previous startup backfill).
    #
    # Behaviour now: inside the trading window we proceed with the intraday scan
    # regardless. We keep an informational log when a daily partition is already
    # present so ops can still see the overlap in the logs.
    if _daily_partition_has_parquet(trading_day):
        log.info(
            "scheduler_intraday_scan_with_daily_present",
            extra={
                "reason": "daily_partition_exists_but_intraday_proceeding",
                "trading_date": trading_day.isoformat(),
                "universe": universe or "default",
            },
        )

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


# ─────────────────────────────────────────────────────────────────────────────
# News ingest job (runs independently of the scan loop).
# This replaces the old `subprocess`-driven provider: we call _build_batch and
# ingest_news_batch in-process so there is nothing to shell out to and nothing
# to configure with an API base URL. Symbol cohort selection reuses the same
# helper the news CLI uses, so "manual run" and "scheduled run" see the same
# universe logic.
# ─────────────────────────────────────────────────────────────────────────────


def _parse_since_expr(expr: Any, fallback_minutes: int) -> int:
    """Accept '60m' / '2h' / integer-minutes string / int. Never throw."""
    if expr is None:
        return max(1, int(fallback_minutes))
    try:
        if isinstance(expr, (int, float)):
            return max(1, int(expr))
        s = str(expr).strip().lower()
        if s.endswith("m"):
            return max(1, int(s[:-1]))
        if s.endswith("h"):
            return max(1, int(s[:-1]) * 60)
        if s.isdigit():
            return max(1, int(s))
    except Exception:
        pass
    return max(1, int(fallback_minutes))


def _run_news_once() -> None:
    """Fire one news-ingest cycle.

    Guarded so a bad feed / missing parquet / transient network error never
    kills the APScheduler job. We log loudly and return so the next tick
    still runs.
    """
    run_id = _now_key()
    try:
        cfg = config.load()
        if not getattr(cfg.news, "enabled", False):
            log.info("news_sched.disabled", extra={"run_id": run_id})
            return

        # Lazy imports: keep scheduler module import-time fast, and avoid
        # pulling the news pipeline into processes that don't use it.
        from app.cli.news_pull import build_intraday_symbol_set
        from app.pipeline.news_provider import _build_batch
        from app.services.news_service import ingest_news_batch

        run_modes = getattr(cfg.news, "run_modes", {}) or {}
        intraday = run_modes.get("intraday") if isinstance(run_modes, dict) else {}
        intraday = intraday if isinstance(intraday, dict) else {}
        cohorts_cfg = intraday.get("cohorts") if isinstance(intraday, dict) else {}
        cohorts_cfg = cohorts_cfg if isinstance(cohorts_cfg, dict) else {}
        fetch_cfg = intraday.get("fetch") if isinstance(intraday, dict) else {}
        fetch_cfg = fetch_cfg if isinstance(fetch_cfg, dict) else {}

        top_movers = cohorts_cfg.get("top_movers") if isinstance(cohorts_cfg, dict) else {}
        top_movers = top_movers if isinstance(top_movers, dict) else {}
        score_thr = cohorts_cfg.get("score_threshold") if isinstance(cohorts_cfg, dict) else {}
        score_thr = score_thr if isinstance(score_thr, dict) else {}

        refresh_minutes = int(getattr(cfg.news, "refresh_minutes", 60) or 60)
        since_minutes = _parse_since_expr(fetch_cfg.get("since"), refresh_minutes)

        # Catch-up window: if the newest stored news partition is older than
        # the poll window (first run, weekend, downtime), widen the window to
        # cover the gap - capped at news.since_days - so items back-fill
        # instead of all being dropped as "outside window".
        try:
            _base = getattr(cfg, "parquet_root", None) or "./backend/parquet"
            _news_root = Path(_base) / "news"
            _parts = (
                sorted(q.name.split("=", 1)[1] for q in _news_root.glob("partition_date=*"))
                if _news_root.exists() else []
            )
            _seed_days = int(getattr(cfg.news, "since_days", 7) or 7)
            _cap_min = _seed_days * 24 * 60
            if _parts:
                _newest = datetime.strptime(_parts[-1], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                _gap_min = int((datetime.now(timezone.utc) - _newest).total_seconds() // 60)
                _target = min(_cap_min, max(_gap_min, 0) + refresh_minutes)
            else:
                _target = _cap_min
            if _target > since_minutes:
                log.info(
                    "news_sched.catchup_window",
                    extra={"from_min": since_minutes, "to_min": _target,
                           "newest_partition": (_parts[-1] if _parts else None)},
                )
                since_minutes = _target
        except Exception:
            log.debug("news_sched: catch-up window calc failed", exc_info=True)

        score_include = bool(score_thr.get("include", True))
        cohorts, rid, as_of = build_intraday_symbol_set(
            watchlist_file=None,
            top_gainers_count=int(top_movers.get("top_gainers_count", 10) or 10),
            top_losers_count=int(top_movers.get("top_losers_count", 10) or 10),
            min_abs_change_pct=float(top_movers.get("min_abs_change_pct", 1.0) or 1.0),
            score_min=(float(score_thr.get("min_score", 70)) if score_include else None),
            score_type=str(score_thr.get("score_type", "full") or "full"),
            max_symbols_score_bucket=(score_thr.get("max_symbols") if score_include else None),
        )
        symbols = cohorts.union() if cohorts else []
        # Always include symbols the user actually holds or shortlisted, so
        # "news on my holdings" has coverage even when they aren't top movers.
        try:
            from app.core.db import get_session as _gs

            _gen = _gs()
            _s = next(_gen)
            try:
                extra: list[str] = []
                try:
                    from app.repos.sql.candidate_pool_repo import CandidatePoolRepo

                    extra += [
                        str(r.get("symbol")).upper()
                        for r in CandidatePoolRepo(session=_s).list_entries(active_only=True)
                        if r.get("symbol")
                    ]
                except Exception:
                    pass
                try:
                    from app.repos.sql.positions_repo import PositionsRepo

                    extra += [
                        str(p.get("symbol")).upper()
                        for p in PositionsRepo(session=_s).list_positions(active=True)
                        if isinstance(p, dict) and p.get("symbol")
                    ]
                except Exception:
                    pass
                seen = set(symbols)
                for sym in extra:
                    if sym not in seen:
                        symbols.append(sym)
                        seen.add(sym)
            finally:
                _gen.close()
        except Exception:
            log.debug("news_sched: holdings symbol union failed", exc_info=True)
        symbol_limit = fetch_cfg.get("max_symbols_per_run")
        if symbol_limit:
            try:
                if len(symbols) > int(symbol_limit):
                    symbols = symbols[: int(symbol_limit)]
            except Exception:
                pass
        if not symbols:
            log.info(
                "news_sched.no_symbols",
                extra={"run_id": run_id, "rid": rid, "as_of": as_of},
            )
            return

        tz_name = getattr(cfg.news, "trading_timezone", None) or "Asia/Kolkata"
        try:
            anchor = datetime.now(ZoneInfo(tz_name))
        except Exception:
            anchor = datetime.now(timezone.utc)

        t0 = time.perf_counter()
        batch = _build_batch(symbols=symbols, since_minutes=since_minutes, anchor=anchor)
        n_items = len(batch.items) if batch and getattr(batch, "items", None) else 0
        if n_items == 0:
            log.info(
                "news_sched.no_items",
                extra={
                    "run_id": run_id,
                    "symbols": len(symbols),
                    "since_min": since_minutes,
                    "ms": round((time.perf_counter() - t0) * 1000, 2),
                },
            )
            return

        ingest_news_batch(batch)
        log.info(
            "news_sched.ok",
            extra={
                "run_id": run_id,
                "symbols": len(symbols),
                "items": n_items,
                "since_min": since_minutes,
                "ms": round((time.perf_counter() - t0) * 1000, 2),
            },
        )
    except Exception:
        log.exception("news_sched.failed", extra={"run_id": run_id})


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

    # Optional: news ingest at its own cadence. Only registered when
    # news is enabled in config so a broken news config can't wedge the
    # scan loop.
    news_enabled = bool(getattr(cfg.news, "enabled", False))
    news_interval = int(getattr(cfg.news, "refresh_minutes", 0) or 0)
    if news_enabled and news_interval > 0:
        sch.add_job(
            func=_run_news_once,
            trigger="interval",
            minutes=max(1, news_interval),
            id="news_every_n_minutes",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=600,
            # First pull shortly after boot so the dashboard isn't empty for
            # a full interval after enabling news.
            next_run_time=datetime.now(timezone.utc) + timedelta(seconds=120),
        )
        log.info(
            "news_scheduler_job_added",
            extra={"interval_min": news_interval},
        )
    else:
        log.info(
            "news_scheduler_job_skipped",
            extra={"news_enabled": news_enabled, "interval_min": news_interval},
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
                "news_enabled": news_enabled,
                "news_interval_min": news_interval,
            },
        )
    except Exception:
        log.info(
            "scheduler_started",
            extra={
                "interval_min": interval,
                "universe": sched_universe or "<default>",
                "news_enabled": news_enabled,
                "news_interval_min": news_interval,
            },
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
