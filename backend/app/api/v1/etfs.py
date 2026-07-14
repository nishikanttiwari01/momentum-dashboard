# backend/app/api/v1/etfs.py
"""ETF momentum watch endpoint (curated list from configs/etf_watch.yaml)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Query

from app.services import etf_service

router = APIRouter(tags=["ETFs"])
log = logging.getLogger(__name__)


@router.get("/etfs/trending", summary="Curated NSE ETFs ranked by recent momentum")
def get_trending_etfs(refresh: bool = Query(False, description="Force re-fetch, bypassing cache")):
    return etf_service.build_snapshot(force_refresh=refresh)
