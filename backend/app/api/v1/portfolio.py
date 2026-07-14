# backend/app/api/v1/portfolio.py
"""Portfolio API: mutual-fund holdings, performance and accumulation signals."""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.services import portfolio_service

router = APIRouter(prefix="/portfolio", tags=["Portfolio"])


@router.get("/overview")
def portfolio_overview(refresh: bool = Query(False, description="Force NAV re-fetch, bypassing cache")):
    return portfolio_service.build_overview(force_refresh=refresh)


@router.get("/nav_history")
def nav_history(
    scheme_code: str = Query(..., description="AMFI/mfapi scheme code, e.g. 120716"),
    range: str = Query("1y", description="1m | 6m | 1y | 5y | max (since inception)"),
):
    """NAV time series for one fund, sliced to the requested range.

    Served from the local mfapi cache (12h TTL) so expanding rows in the UI
    doesn't hammer api.mfapi.in."""
    return portfolio_service.build_nav_history(scheme_code=scheme_code, range_key=range)
