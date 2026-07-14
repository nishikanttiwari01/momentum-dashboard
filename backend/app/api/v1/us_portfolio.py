"""BUY-only US portfolio endpoints."""
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field, PositiveFloat, field_validator

from app.services import us_portfolio_service as service

router = APIRouter(prefix="/portfolio/us", tags=["Portfolio"])


class BuyTransactionCreate(BaseModel):
    instrument_id: Literal["qqq"]
    purchased_at: datetime
    quantity: PositiveFloat
    price_usd: PositiveFloat
    fees_usd: Annotated[float, Field(ge=0)] = 0

    @field_validator("purchased_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timezone is required")
        return value


@router.get("/overview")
def overview(refresh: bool = Query(False)):
    return service.build_overview(force_refresh=refresh)


@router.get("/{instrument_id}/history")
def history(
    instrument_id: Literal["qqq"],
    range: Literal["1m", "6m", "1y", "5y", "max"] = "1y",
):
    return service.build_history(instrument_id, range)


@router.post("/transactions", status_code=201)
def create_transaction(payload: BuyTransactionCreate):
    return service.add_buy(payload.model_dump())
