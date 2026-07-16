from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.services.market_index_service import (
    MarketIndexHistory,
    MarketIndexService,
    MarketIndexUnavailable,
)


router = APIRouter(prefix="/market-indices", tags=["Market Indices"])


def get_market_index_service() -> MarketIndexService:
    return MarketIndexService()


@router.get("/{key}/history", response_model=MarketIndexHistory)
def get_market_index_history(
    key: str,
    range_: Literal["1m", "6m", "1y", "5y"] = Query("1y", alias="range"),
    service: MarketIndexService = Depends(get_market_index_service),
) -> MarketIndexHistory:
    try:
        return service.build_history(key, range_)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except MarketIndexUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
