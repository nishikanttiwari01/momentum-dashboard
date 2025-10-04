from __future__ import annotations

from datetime import datetime
from typing import Optional, Literal
import os
import logging

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

def _enforce_ingest_auth() -> None:
    cfg = load().news.ingest or {}
    if cfg.get("require_token"):
        token_env = cfg.get("token_env") or "NEWS_INGEST_TOKEN"
        if not os.getenv(token_env):
            raise PermissionError(
                f"Ingest requires server env {token_env} to be set (bearer token enforcement)."
            )

def ingest_news_batch(batch: NewsIngestBatch) -> None:
    log.info("news.service.ingest_start", extra={"count": len(batch.items)})
    _enforce_ingest_auth()
    ensure_news_storage_ready()
    repo_ingest_batch(batch)
    log.info("news.service.ingest_complete", extra={"count": len(batch.items)})


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
        },
    )
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
        extra={"symbol": symbol, "items": len(items), "next_page": next_page},
    )
    return items, next_page


def reason_for_move_candidates(
    symbol: str,
    at: datetime,
    lookback_min: int,
    min_confidence: Optional[int],
) -> list[NewsAttributionItem]:
    log.info(
        "news.service.reason_start",
        extra={
            "symbol": symbol,
            "at": at.isoformat(),
            "lookback_min": lookback_min,
            "min_confidence": min_confidence,
        },
    )
    ensure_news_storage_ready()
    items = repo_attribute_move(
        symbol=symbol,
        at=at,
        lookback_min=lookback_min,
        min_confidence=min_confidence,
    )
    log.info(
        "news.service.reason_complete",
        extra={"symbol": symbol, "items": len(items)},
    )
    return items


