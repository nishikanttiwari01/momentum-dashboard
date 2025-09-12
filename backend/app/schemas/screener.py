# backend/app/schemas/screener.py
from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field


class Badge(BaseModel):
    # Phase7: support new compact badge fields while keeping old ones (back-compat)
    code: Optional[str] = None
    text: Optional[str] = None
    key: Optional[str] = None
    label: Optional[str] = None
    color: Optional[str] = None


class ScreenerRow(BaseModel):
    # Identity & basics
    symbol: str
    name: Optional[str] = None
    sector: Optional[str] = None

    # Price & today's change
    last: Optional[float] = None
    change_pct: Optional[float] = None

    # Phase7: 1-week deltas
    wk_change: Optional[float] = None
    wk_change_pct: Optional[float] = None

    # Badges (compact + legacy fields)
    badges: List[Badge] = Field(default_factory=list)

    # Score & strength
    score: Optional[int] = None   # 0–100 (as per your example)
    strength: Optional[str] = None

    # Indicators & returns
    rsi: Optional[float] = None
    adx: Optional[float] = None
    ret_12_1m: Optional[float] = None
    ret_6m: Optional[float] = None
    ret_3m: Optional[float] = None
    ret_1m: Optional[float] = None
    # NOTE: ret_1w REMOVED to avoid leaking into API responses

    # Context metrics
    pct_from_52w_high: Optional[float] = None
    atr_pct: Optional[float] = None
    liquidity: Optional[float] = None
    vol_spike: Optional[float] = None
    pct_today: Optional[float] = None

    # Flags & lineage
    buy: Optional[bool] = None
    reason: Optional[str] = None
    source: Optional[str] = None
    stale: Optional[bool] = None

    run_id: Optional[str] = None
    as_of: Optional[str] = None
    last_index: Optional[str] = None


class Pagination(BaseModel):
    page: int
    per_page: int
    total: int
    next_cursor: Optional[str] = None


class ScreenerList(BaseModel):
    items: List[ScreenerRow]
    pagination: Pagination
    as_of: Optional[str] = None
    run_id: Optional[str] = None
