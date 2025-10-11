# app/services/news_service.py
from __future__ import annotations

from datetime import datetime
from typing import Optional, Literal
import os
import logging
import time  # ✨ added
import uuid  # ✨ added

log = logging.getLogger(__name__)

from app.core.config import load

# 👉 use your generated models location
from app.schemas.generated.models import (
    NewsIngestBatch,
    NewsCard,
    NewsAttributionItem,
)

from app.repos.parquet.news_repo import (
    ensure_news_storage_ready,
    repo_ingest_batch,
    repo_list_news,
    repo_attribute_move,
)

# ──────────────────────────────────────────────────────────────────────────────
# Lightweight logging bootstrap (non-invasive)
# ──────────────────────────────────────────────────────────────────────────────

def _configure_logging_if_needed(default_level: str = "INFO") -> None:
    """
    Initialize root logging only if the app hasn't configured it.
    Respects LOG_LEVEL env (DEBUG/INFO/WARN/ERROR).
    """
    root = logging.getLogger()
    if not root.handlers:
        level_name = os.getenv("LOG_LEVEL", default_level).upper()
        level = getattr(logging, level_name, logging.INFO)
        logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
        log.debug("logging.configured", extra={"level": level_name})

def _runid() -> str:
    """Per-process correlation id for grouping logs across calls."""
    if not hasattr(_runid, "_id"):
        setattr(_runid, "_id", uuid.uuid4().hex[:12])
    return getattr(_runid, "_id")

def _t0() -> float:
    return time.perf_counter()

def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000.0, 2)

def _exc(context: str, **extra):
    extra = {"run_id": _runid(), **extra}
    log.exception(context, extra=extra)

# Ensure minimal logging if invoked standalone or from scripts
_configure_logging_if_needed()

# ──────────────────────────────────────────────────────────────────────────────
# Service
# ──────────────────────────────────────────────────────────────────────────────

def _enforce_ingest_auth() -> None:
    cfg = load().news.ingest or {}
    if cfg.get("require_token"):
        token_env = cfg.get("token_env") or "NEWS_INGEST_TOKEN"
        if not os.getenv(token_env):
            # Don't log secrets; just the env var name
            log.error("news.service.auth_missing_token", extra={"token_env": token_env, "run_id": _runid()})
            raise PermissionError(
                f"Ingest requires server env {token_env} to be set (bearer token enforcement)."
            )
        else:
            log.debug("news.service.auth_token_present", extra={"token_env": token_env, "run_id": _runid()})

def ingest_news_batch(batch: NewsIngestBatch) -> None:
    t0 = _t0()
    # Original line kept; augmented with run_id
    log.info("news.service.ingest_start", extra={"count": len(batch.items), "run_id": _runid()})
    try:
        _enforce_ingest_auth()
        ensure_news_storage_ready()
        repo_ingest_batch(batch)
        log.info(
            "news.service.ingest_complete",
            extra={"count": len(batch.items), "ms": _ms(t0), "run_id": _runid()},
        )
    except PermissionError:
        # Auth failures are expected control-path errors; log at WARNING for signal
        log.warning("news.service.ingest_denied", extra={"count": len(batch.items), "ms": _ms(t0), "run_id": _runid()})
        raise
    except Exception:
        _exc("news.service.ingest_exception", count=len(batch.items))
        raise


def list_news_for_symbol(
    symbol: str,
    from_dt: datetime,
    to_dt: datetime,
    page: int,
    per_page: int,
    min_confidence: Optional[int],
    event_filter: Optional[list[str]],
    sort: Literal["impact_desc", "published_desc", "confirmed_desc"],
) -> tuple[list[NewsCard], Optional[int]]:
    t0 = _t0()
    log.info(
        "news.service.list_start",
        extra={
            "symbol": symbol,
            "from": from_dt.isoformat(),
            "to": to_dt.isoformat(),
            "page": page,
            "per_page": per_page,
            "min_confidence": min_confidence,
            "event_filter": event_filter,
            "sort": sort,
            "run_id": _runid(),
        },
    )
    try:
        ensure_news_storage_ready()
        items, next_page = repo_list_news(
            symbol=symbol,
            from_dt=from_dt,
            to_dt=to_dt,
            page=page,
            per_page=per_page,
            min_confidence=min_confidence,
            event_filter=event_filter,
            sort=sort,
        )
        log.info(
            "news.service.list_complete",
            extra={
                "symbol": symbol,
                "items": len(items),
                "next_page": next_page,
                "ms": _ms(t0),
                "run_id": _runid(),
            },
        )
        # Extra debug for pagination edges
        if next_page is None:
            log.debug("news.service.list_no_more_pages", extra={"symbol": symbol, "run_id": _runid()})
        return items, next_page
    except Exception:
        _exc(
            "news.service.list_exception",
            symbol=symbol,
            page=page,
            per_page=per_page,
            sort=sort,
        )
        raise


def list_all_news(
    symbol: Optional[str],
    from_dt: datetime,
    to_dt: datetime,
    page: int,
    per_page: int,
    min_confidence: Optional[int],
    event_filter: Optional[list[str]],
    sort: Literal["impact_desc", "published_desc", "confirmed_desc"],
) -> tuple[list[NewsCard], Optional[int]]:
    t0 = _t0()
    log.info(
        "news.service.list_all_start",
        extra={
            "from": from_dt.isoformat(),
            "to": to_dt.isoformat(),
            "page": page,
            "per_page": per_page,
            "min_confidence": min_confidence,
            "event_filter": event_filter,
            "sort": sort,
            "run_id": _runid(),
        },
    )
    try:
        ensure_news_storage_ready()
        items, next_page = repo_list_news(
            symbol=symbol,
            from_dt=from_dt,
            to_dt=to_dt,
            page=page,
            per_page=per_page,
            min_confidence=min_confidence,
            event_filter=event_filter,
            sort=sort,
        )
        log.info(
            "news.service.list_all_complete",
            extra={
                "symbol": symbol or "*",
                "items": len(items),
                "next_page": next_page,
                "ms": _ms(t0),
                "run_id": _runid(),
            },
        )
        if next_page is None:
            log.debug("news.service.list_all_no_more_pages", extra={"symbol": symbol or "*", "run_id": _runid()})
        return items, next_page
    except Exception:
        _exc(
            "news.service.list_all_exception",
            symbol=symbol or "*",
            page=page,
            per_page=per_page,
            sort=sort,
        )
        raise


def reason_for_move_candidates(
    symbol: str,
    at: datetime,
    lookback_min: int,
    min_confidence: Optional[int],
) -> list[NewsAttributionItem]:
    t0 = _t0()
    log.info(
        "news.service.reason_start",
        extra={
            "symbol": symbol,
            "at": at.isoformat(),
            "lookback_min": lookback_min,
            "min_confidence": min_confidence,
            "run_id": _runid(),
        },
    )
    try:
        ensure_news_storage_ready()
        items = repo_attribute_move(
            symbol=symbol,
            at=at,
            lookback_min=lookback_min,
            min_confidence=min_confidence,
        )
        log.info(
            "news.service.reason_complete",
            extra={
                "symbol": symbol,
                "items": len(items),
                "ms": _ms(t0),
                "run_id": _runid(),
            },
        )
        # Helpful debug on top attribution if present
        if items:
            top = items[0]
            log.debug(
                "news.service.reason_top",
                extra={
                    "symbol": symbol,
                    "top_cluster": getattr(top, "cluster_id", None),
                    "top_decision": getattr(top, "decision", None),
                    "top_impact": getattr(top, "impact_score", None),
                    "run_id": _runid(),
                },
            )
        return items
    except Exception:
        _exc(
            "news.service.reason_exception",
            symbol=symbol,
            lookback_min=lookback_min,
            min_confidence=min_confidence,
        )
        raise
