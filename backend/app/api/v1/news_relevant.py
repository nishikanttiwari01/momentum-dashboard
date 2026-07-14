# backend/app/api/v1/news_relevant.py
"""Personalised news: aggregates recent news for symbols the user actually
holds or is watching (active positions + candidate pool), instead of a
generic all-market feed."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Query

log = logging.getLogger(__name__)

router = APIRouter(tags=["News"])


def _portfolio_symbols() -> Dict[str, List[str]]:
    """Symbols grouped by why they matter: active trades, candidate pool."""
    groups: Dict[str, List[str]] = {"positions": [], "candidates": []}

    try:
        from app.core.db import get_session
        gen = get_session()
        session = next(gen)
        try:
            # Active positions
            try:
                from app.repos.sql.positions_repo import PositionsRepo  # type: ignore

                repo = PositionsRepo(session=session)
                for p in repo.list_positions(active=True) or []:
                    sym = p.get("symbol") if isinstance(p, dict) else None
                    if sym:
                        groups["positions"].append(str(sym).upper())
            except Exception:
                log.debug("news_relevant: positions repo unavailable", exc_info=True)

            # Candidate pool
            try:
                from app.repos.sql.candidate_pool_repo import CandidatePoolRepo

                pool = CandidatePoolRepo(session=session)
                for row in pool.list_entries(active_only=True):
                    sym = row.get("symbol")
                    if sym:
                        groups["candidates"].append(str(sym).upper())
            except Exception:
                log.debug("news_relevant: pool repo unavailable", exc_info=True)
        finally:
            gen.close()
    except Exception:
        log.debug("news_relevant: db unavailable", exc_info=True)

    return groups


@router.get("/news/relevant")
def relevant_news(
    days: int = Query(3, ge=1, le=14),
    per_symbol: int = Query(3, ge=1, le=10),
):
    """News for held/watched symbols only. Returns items grouped per symbol."""
    groups = _portfolio_symbols()
    now = datetime.now(timezone.utc)
    from_dt = now - timedelta(days=days)

    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for reason, symbols in groups.items():
        for sym in symbols:
            if sym in seen:
                continue
            seen.add(sym)
            items: List[Any] = []
            try:
                from app.services.news_service import list_news_for_symbol

                cards, _next = list_news_for_symbol(
                    symbol=sym,
                    from_dt=from_dt,
                    to_dt=now,
                    page=1,
                    per_page=per_symbol,
                    min_confidence=None,
                    event_filter=None,
                    sort="published_desc",
                )
                for c in cards or []:
                    items.append(c.model_dump() if hasattr(c, "model_dump") else c)
            except Exception:
                log.debug("news_relevant: fetch failed for %s", sym, exc_info=True)
            out.append({"symbol": sym, "why": reason, "items": items})

    return {
        "generated_at": now.isoformat(),
        "window_days": days,
        "symbols": out,
        "total_items": sum(len(s["items"]) for s in out),
    }


@router.post("/news/refresh")
def refresh_news():
    """Manually trigger one news-ingest cycle in the background.

    Useful right after enabling news, instead of waiting for the scheduler
    interval. Returns immediately; check /health/data for the news dataset
    timestamp to confirm ingestion.
    """
    import threading

    def _runner() -> None:
        try:
            from app.workers.scheduler import _run_news_once

            _run_news_once()
        except Exception:
            log.exception("manual news refresh failed")

    t = threading.Thread(target=_runner, name="manual-news-refresh", daemon=True)
    t.start()
    return {"status": "started", "note": "Ingest running in background; watch /health/data → news."}


@router.get("/news/catalysts")
def news_catalysts(symbols: str = Query(..., description="Comma-separated symbols, e.g. TRENT.NS,ITDC.NS")):
    """Most recent news item per symbol (last 3 days) — used by Top Movers to
    show a possible catalyst for the move."""
    from datetime import timedelta as _td

    now = datetime.now(timezone.utc)
    out: Dict[str, Any] = {}
    for raw in symbols.split(","):
        sym = raw.strip().upper()
        if not sym:
            continue
        try:
            from app.services.news_service import list_news_for_symbol

            cards, _ = list_news_for_symbol(
                symbol=sym,
                from_dt=now - _td(days=3),
                to_dt=now,
                page=1,
                per_page=1,
                min_confidence=None,
                event_filter=None,
                sort="published_desc",
            )
            if cards:
                c = cards[0]
                d = c.model_dump() if hasattr(c, "model_dump") else dict(c)
                out[sym] = {
                    "headline": d.get("headline") or d.get("title"),
                    "url": d.get("url") or d.get("link"),
                    "source": d.get("source"),
                    "published_at": d.get("published_at") or d.get("published"),
                }
        except Exception:
            log.debug("catalyst lookup failed for %s", sym, exc_info=True)
    return {"generated_at": now.isoformat(), "catalysts": out}
