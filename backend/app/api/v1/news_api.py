from __future__ import annotations

from datetime import datetime, date
from typing import Literal, Optional
import zoneinfo
import logging

from fastapi import APIRouter, Query, Path, Body, HTTPException

# 👉 use your generated models location
from app.schemas.generated.models import (
    NewsListResponse,
    NewsMoveAttributionResponse,
    NewsIngestBatch,
    Window,
)

from app.core.config import load
from app.services.news_service import (
    list_news_for_symbol,
    reason_for_move_candidates,
    ingest_news_batch,
)

log = logging.getLogger(__name__)


router = APIRouter(tags=["News"])

def _ist() -> zoneinfo.ZoneInfo:
    tz = load().news.trading_timezone or "Asia/Kolkata"
    return zoneinfo.ZoneInfo(tz)

def _resolve_window(
    on: Optional[date],
    align: Literal["trading_day", "calendar_day"],
    from_dt: Optional[datetime],
    to_dt: Optional[datetime],
) -> tuple[datetime, datetime]:
    if from_dt and to_dt:
        return from_dt, to_dt
    if on:
        ist = _ist()
        if align == "trading_day":
            start = datetime(on.year, on.month, on.day, 9, 0, 0, tzinfo=ist)
            end = datetime(on.year, on.month, on.day, 16, 30, 0, tzinfo=ist)
        else:
            start = datetime(on.year, on.month, on.day, 0, 0, 0, tzinfo=ist)
            end = datetime(on.year, on.month, on.day, 23, 59, 59, tzinfo=ist)
        return start, end
    raise HTTPException(status_code=400, detail="Provide either on+align or from+to")

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
        },
    )
    from_dt, to_dt = _resolve_window(on, align, from_, to)
    event_filter = [e.strip() for e in event.split(",")] if event else None
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
    log.info("news.api.list_response", extra={"symbol": symbol, "items": len(items), "next_page": next_page})
    return NewsListResponse(
        symbol=symbol,
        window=Window(from_=from_dt, to=to_dt),
        page=page,
        per_page=per_page,
        items=items,
        next_page=next_page,
        note=None if items else "No consensus-grade news found in window",
    )


@router.get("/moves/{symbol}/reason", response_model=NewsMoveAttributionResponse)
def reason_for_move(
    symbol: str = Path(..., description="e.g., RELIANCE.NS"),
    at: datetime = Query(..., description="Timestamp near the observed move (IST recommended)"),
    lookback_min: int = Query(240, ge=15, le=1440),
    min_confidence: Optional[int] = Query(None, ge=1, le=3),
) -> NewsMoveAttributionResponse:
    log.info(
        "news.api.reason_request",
        extra={"symbol": symbol, "at": at.isoformat(), "lookback_min": lookback_min, "min_confidence": min_confidence},
    )
    items = reason_for_move_candidates(
        symbol=symbol,
        at=at,
        lookback_min=lookback_min,
        min_confidence=min_confidence,
    )
    log.info("news.api.reason_response", extra={"symbol": symbol, "items": len(items)})
    return NewsMoveAttributionResponse(symbol=symbol, at=at, lookback_min=lookback_min, items=items)


@router.post("/news/ingest", status_code=202)
def ingest_news(batch: NewsIngestBatch = Body(...)) -> dict:
    log.info("news.api.ingest_request", extra={"items": len(batch.items) if batch and batch.items else 0})
    ingest_news_batch(batch)
    log.info("news.api.ingest_response", extra={"items": len(batch.items) if batch and batch.items else 0})
    return {"status": "accepted", "count": len(batch.items)}

