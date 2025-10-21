from __future__ import annotations

import logging
import os
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import yaml

from app.alerts import orchestrator
from app.alerts.types import Mode
from app.core.config import REPO_ROOT
from app.core.db import get_session
from app.repos.parquet.scores_repo import ScoresRepo

logger = logging.getLogger(__name__)


def _coerce_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _resolve_alerts_cfg(settings_payload: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not settings_payload:
        return None

    alerts_cfg = settings_payload.get("alerts")
    if isinstance(alerts_cfg, dict) and alerts_cfg:
        # Some configs wrap under {"alerts": {...}}
        return alerts_cfg.get("alerts", alerts_cfg)

    path_hint = os.getenv("ALERTS_CONFIG_PATH") or settings_payload.get("alerts_config_path")
    if not path_hint:
        return None

    path = Path(path_hint)
    if not path.is_absolute():
        path = (REPO_ROOT / path).resolve()

    if not path.exists():
        logger.warning("alerts_config_path_missing", extra={"path": str(path)})
        return None

    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.exception("alerts_config_load_failed", extra={"path": str(path), "error": str(exc)})
        return None

    if isinstance(loaded, dict):
        return loaded.get("alerts", loaded)
    return None


def _make_metric_getter(metrics_by_symbol: Dict[str, Dict[str, Any]]) -> Callable[[str, str], Any]:
    def _getter(symbol: str, name: str) -> Any:
        data = metrics_by_symbol.get(symbol)
        if not data:
            return None
        return data.get(name)

    return _getter


def evaluate_momentum_crossups(run_id: Optional[str], settings_payload: Optional[Dict[str, Any]], as_of_str: Optional[str] = None) -> int:
    """
    Lightweight bridge between the screening job output and the alerts orchestrator.

    Returns the number of alert events created (best-effort; errors are swallowed and logged).
    """
    alerts_cfg = _resolve_alerts_cfg(settings_payload)
    if not alerts_cfg:
        logger.info("alerts_config_not_available_skip", extra={"run_id": run_id})
        return 0

    if not run_id:
        logger.info("alerts_run_id_missing_skip")
        return 0

    scores_repo = ScoresRepo()
    try:
        rows, _, _, resolved_as_of = scores_repo.read(
            run_id=run_id,
            as_of_str=None,
            filters={},
            sort="",
            page=1,
            per_page=5000,
            columns=None,
        )
    except Exception as exc:
        logger.exception("alerts_scores_read_failed", extra={"run_id": run_id, "error": str(exc)})
        return 0

    # Retry #1: if nothing came back for run_id, try explicit as_of (if provided)
    if not rows and as_of_str:
        try:
            rows, _, _, resolved_as_of = scores_repo.read(
                run_id=None, as_of_str=as_of_str,
                filters={}, sort="", page=1, per_page=5000, columns=None,
            )
            if rows:
                logger.info("alerts_scores_retry_asof_only", extra={"as_of": as_of_str})
        except Exception:
            pass
    # Retry #2: fall back to latest committed DAILY snapshot
    if not rows:
        try:
            rows, _, _, resolved_as_of = scores_repo.read(
                run_id=None, as_of_str=None,
                filters={}, sort="", page=1, per_page=5000, columns=None,
            )
            if rows:
                logger.info("alerts_scores_retry_latest_daily", extra={"run_id": run_id})
        except Exception:
            pass
    is_eod_snapshot = any(bool((row or {}).get("is_eod")) for row in rows if isinstance(row, dict))
    if not is_eod_snapshot:
        candidate = resolved_as_of or as_of_str or ScoresRepo.run_id_to_date(run_id)
        if isinstance(candidate, str):
            candidate_clean = candidate.strip()
            if candidate_clean and ("T" not in candidate_clean) and len(candidate_clean) == 10:
                is_eod_snapshot = True

    alert_mode = Mode.EOD if is_eod_snapshot else Mode.INTRADAY
    try:
        logger.info(
            "alerts_snapshot_mode",
            extra={
                "run_id": run_id,
                "resolved_as_of": resolved_as_of,
                "as_of_requested": as_of_str,
                "is_eod": is_eod_snapshot,
            },
        )
    except Exception:
        pass

    metrics_by_symbol = {
        row["symbol"]: row for row in rows if isinstance(row.get("symbol"), str)
    }

    if not metrics_by_symbol:
        logger.info("alerts_metrics_empty_skip", extra={"run_id": run_id})
        return 0

    trading_date = (
        _coerce_date(resolved_as_of)
        or _coerce_date(as_of_str)
        or _coerce_date(ScoresRepo.run_id_to_date(run_id))
        or datetime.now(timezone.utc).date()
    )

    symbols = list(metrics_by_symbol.keys())
    metric_getter = _make_metric_getter(metrics_by_symbol)
    now_utc = datetime.now(timezone.utc)

    gen = get_session()
    session = next(gen)
    try:
        try:
            conn = session.connection()
        except Exception:
            bind = session.get_bind()
            conn = bind.connect() if bind is not None else None

        if conn is None:
            logger.warning("alerts_db_connection_unavailable")
            return 0

        created_ids = orchestrator.run(
            conn,
            alerts_cfg=alerts_cfg,
            symbols=symbols,
            mode=alert_mode,
            trading_date=trading_date,
            now_utc=now_utc,
            metric_getter=metric_getter,
            run_ctx={"triggered_by": "SCHEDULE", "snapshot_mode": alert_mode.value},
        )
        try:
            session.commit()
        except Exception:
            session.rollback()
        return len(created_ids or [])
    except Exception as exc:
        logger.exception("alerts_orchestrator_failed", extra={"run_id": run_id, "error": str(exc)})
        return 0
    finally:
        try:
            session.close()
        except Exception:
            pass
        try:
            gen.close()
        except Exception:
            pass
