# app/api/v1/news_api.py
from __future__ import annotations

from datetime import datetime, date
from typing import Literal, Optional
import zoneinfo
import logging
import os  # ✨ added
import time  # ✨ added
import uuid  # ✨ added

from fastapi import APIRouter, Query, Path, Body, HTTPException

# 👉 use your generated models location
from app.schemas.generated.models import (
    NewsListResponse,
    NewsWindowListResponse,
    NewsMoveAttributionResponse,
    NewsIngestBatch,
    Window,
)

from app.core.config import load
from app.services.news_service import (
    list_news_for_symbol,
    list_all_news,
    reason_for_move_candidates,
    ingest_news_batch,
)

log = logging.getLogger(__name__)
router = APIRouter(tags=["News"])

# ──────────────────────────────────────────────────────────────────────────────
# Lightweight logging bootstrap (non-invasive)
# ──────────────────────────────────────────────────────────────────────────────

def _configure_logging_if_needed(default_level: str = "INFO") -> None:
    """Initialize root logging only if the app hasn't configured it. Respects LOG_LEVEL."""
    root = logging.getLogger()
    if not root.handlers:
        level_name = os.getenv("LOG_LEVEL", default_level).upper()
        level = getattr(logging, level_name, logging.INFO)
        logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
        log.debug("logging.configured", extra={"level": level_name})

def _runid() -> str:
    """Per-process correlation id for grouping logs across requests in dev/CLI."""
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

# Ensure minimal logging if invoked standalone (FastAPI usually configures logging itself)
_configure_logging_if_needed()

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _ist() -> zoneinfo.ZoneInfo:
    tz = (getattr(load().news, "trading_timezone", None) or "Asia/Kolkata")
    try:
        z = zoneinfo.ZoneInfo(tz)
        log.debug("news.api.tz_resolved", extra={"tz": tz, "run_id": _runid()})
        return z
    except Exception:
        # Fallback to Asia/Kolkata, log once
        _exc("news.api.tz_invalid", tz=tz)
        return zoneinfo.ZoneInfo("Asia/Kolkata")

def _resolve_window(
    on: Optional[date],
    align: Literal["trading_day", "calendar_day"],
    from_dt: Optional[datetime],
    to_dt: Optional[datetime],
) -> tuple[datetime, datetime]:
    """Resolve the requested time window; raises HTTP 400 if insufficient args."""
    if from_dt and to_dt:
        log.debug(
            "news.api.window_direct",
            extra={"from": from_dt.isoformat(), "to": to_dt.isoformat(), "run_id": _runid()},
        )
        return from_dt, to_dt
    if on:
        ist = _ist()
        if align == "trading_day":
            start = datetime(on.year, on.month, on.day, 9, 0, 0, tzinfo=ist)
            end = datetime(on.year, on.month, on.day, 16, 30, 0, tzinfo=ist)
        else:
            start = datetime(on.year, on.month, on.day, 0, 0, 0, tzinfo=ist)
            end = datetime(on.year, on.month, on.day, 23, 59, 59, tzinfo=ist)
        log.debug(
            "news.api.window_from_on",
            extra={"on": on.isoformat(), "align": align, "from": start.isoformat(), "to": end.isoformat(), "run_id": _runid()},
        )
        return start, end
    log.warning("news.api.window_bad_args", extra={"on": on, "from": from_dt, "to": to_dt, "run_id": _runid()})
    raise HTTPException(status_code=400, detail="Provide either on+align or from+to")

# ──────────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/news", response_model=NewsListResponse)
def list_news(
    symbol: str = Query(..., description="e.g., RELIANCE.NS"),
    on: Optional[date] = Query(None),
    align: Literal["trading_day", "calendar_day"] = Query("trading_day"),
    from_: Optional[datetime] = Query(None, alias="from"),
    to: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
    min_confidence: Optional[int] = Query(None, ge=1, le=3),
    event: Optional[str] = Query(None, description="Comma-separated event types (e.g., results,pledge,order_win)"),
    sort: Literal["impact_desc", "published_desc", "confirmed_desc"] = Query("impact_desc"),
) -> NewsListResponse:
    t0 = _t0()
    log.info(
        "news.api.list_request",
        extra={
            "symbol": symbol,
            "on": on.isoformat() if on else None,
            "align": align,
            "from": from_.isoformat() if from_ else None,
            "to": to.isoformat() if to else None,
            "page": page,
            "per_page": per_page,
            "min_confidence": min_confidence,
            "event": event,
            "sort": sort,
            "run_id": _runid(),
        },
    )
    try:
        from_dt, to_dt = _resolve_window(on, align, from_, to)
        event_filter = [e.strip() for e in event.split(",")] if event else None
        if event_filter is not None:
            log.debug("news.api.event_filter", extra={"events": event_filter, "run_id": _runid()})
        items, next_page = list_news_for_symbol(
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
            "news.api.list_response",
            extra={
                "symbol": symbol,
                "items": len(items),
                "next_page": next_page,
                "ms": _ms(t0),
                "run_id": _runid(),
            },
        )
        return NewsListResponse(
            symbol=symbol,
            window=Window(**{"from": from_dt, "to": to_dt}),
            page=page,
            per_page=per_page,
            items=items,
            next_page=next_page,
            note=None if items else "No consensus-grade news found in window",
        )
    except HTTPException:
        # already meaningful; just time it
        log.warning("news.api.list_http_error", extra={"ms": _ms(t0), "run_id": _runid()})
        raise
    except Exception:
        _exc(
            "news.api.list_exception",
            symbol=symbol,
            on=(on.isoformat() if on else None),
            align=align,
            page=page,
            per_page=per_page,
        )
        raise


@router.get("/moves/{symbol}/reason", response_model=NewsMoveAttributionResponse)
def reason_for_move(
    symbol: str = Path(..., description="e.g., RELIANCE.NS"),
    at: datetime = Query(..., description="Timestamp near the observed move (IST recommended)"),
    lookback_min: int = Query(240, ge=15, le=1440),
    min_confidence: Optional[int] = Query(None, ge=1, le=3),
) -> NewsMoveAttributionResponse:
    t0 = _t0()
    log.info(
        "news.api.reason_request",
        extra={"symbol": symbol, "at": at.isoformat(), "lookback_min": lookback_min, "min_confidence": min_confidence, "run_id": _runid()},
    )
    try:
        items = reason_for_move_candidates(
            symbol=symbol,
            at=at,
            lookback_min=lookback_min,
            min_confidence=min_confidence,
        )
        log.info(
            "news.api.reason_response",
            extra={"symbol": symbol, "items": len(items), "ms": _ms(t0), "run_id": _runid()},
        )
        return NewsMoveAttributionResponse(symbol=symbol, at=at, lookback_min=lookback_min, items=items)
    except Exception:
        _exc("news.api.reason_exception", symbol=symbol, at=at.isoformat(), lookback_min=lookback_min)
        raise


@router.post("/news/ingest", status_code=202)
def ingest_news(batch: NewsIngestBatch = Body(...)) -> dict:
    t0 = _t0()
    log.info(
        "news.api.ingest_request",
        extra={"items": len(batch.items) if batch and batch.items else 0, "run_id": _runid()},
    )
    try:
        ingest_news_batch(batch)
        log.info(
            "news.api.ingest_response",
            extra={"items": len(batch.items) if batch and batch.items else 0, "ms": _ms(t0), "run_id": _runid()},
        )
        return {"status": "accepted", "count": len(batch.items)}
    except Exception:
        _exc("news.api.ingest_exception", items=len(batch.items) if batch and batch.items else 0)
        raise
    
@router.get(
    "/news/list",
    response_model=NewsWindowListResponse,
    summary="List news across all symbols for a trading window",
)
def list_all_news_endpoint(
    symbol: Optional[str] = Query(None, description="Optional symbol filter (e.g., RELIANCE.NS)"),
    on: Optional[date] = Query(None),
    align: Literal["trading_day", "calendar_day"] = Query("trading_day"),
    from_: Optional[datetime] = Query(None, alias="from"),
    to: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=500),
    min_confidence: Optional[int] = Query(None, ge=1, le=5),
    event: Optional[str] = Query(None, description="CSV of event types"),
    sort: Literal["impact_desc", "published_desc", "confirmed_desc"] = Query("impact_desc"),
) -> NewsWindowListResponse:
    """
    Lists news cards across the universe for the requested trading window.
    Provide either `on` (+ optional `align`) or explicit `from`/`to` timestamps.
    """
    from_dt, to_dt = _resolve_window(on, align, from_, to)

    event_filter = None
    if event:
        event_filter = [x.strip() for x in event.split(",") if x.strip()]

    t0 = _t0()
    try:
        items, next_page = list_all_news(
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
            "news.api.list_all_response",
            extra={"symbol": symbol or "*", "items": len(items), "next_page": next_page, "ms": _ms(t0), "run_id": _runid()},
        )
        return NewsWindowListResponse(
            window=Window(**{"from": from_dt, "to": to_dt}),
            page=page,
            per_page=per_page,
            items=items,
            next_page=next_page,
            note=None if items else "No consensus-grade news found in window",
        )
    except HTTPException:
        log.warning("news.api.list_all_http_error", extra={"ms": _ms(t0), "run_id": _runid()})
        raise
    except Exception:
        _exc(
            "news.api.list_all_exception",
            symbol=symbol,
            on=(on.isoformat() if on else None),
            align=align,
            page=page,
            per_page=per_page,
        )
        raise
