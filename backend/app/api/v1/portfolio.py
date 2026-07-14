# backend/app/api/v1/portfolio.py
"""Portfolio API: mutual-fund holdings, performance and accumulation signals."""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, PositiveFloat, model_validator

from app.services import portfolio_service

router = APIRouter(prefix="/portfolio", tags=["Portfolio"])


class FundBuyCreate(BaseModel):
    instrument_id: str
    date: date
    amount: Optional[PositiveFloat] = None
    units: Optional[PositiveFloat] = None
    nav: PositiveFloat
    fees: float = Field(0, ge=0)

    @model_validator(mode="after")
    def amount_or_units(self):
        if self.amount is None and self.units is None:
            raise ValueError("Enter amount or units")
        return self


@router.get("/overview")
def portfolio_overview(refresh: bool = Query(False, description="Force NAV re-fetch, bypassing cache")):
    return portfolio_service.build_overview(force_refresh=refresh)


@router.get("/nav_history")
def nav_history(
    scheme_code: str = Query(..., description="AMFI/mfapi scheme code, e.g. 120716"),
    instrument_id: Optional[str] = Query(None),
    range: str = Query("1y", description="1m | 6m | 1y | 5y | max (since inception)"),
):
    """NAV time series for one fund, sliced to the requested range.

    Served from the local mfapi cache (12h TTL) so expanding rows in the UI
    doesn't hammer api.mfapi.in."""
    return portfolio_service.build_nav_history(scheme_code=scheme_code, range_key=range, instrument_id=instrument_id)


@router.post("/transactions", status_code=201)
def create_transaction(payload: FundBuyCreate):
    try:
        return portfolio_service.append_buy(payload.model_dump(mode="json"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
