# backend/app/schemas/screener.py
from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel


class Badge(BaseModel):
    key: str
    label: str
    color: str  # e.g., "green", "orange", "red"


class ScreenerRow(BaseModel):
    symbol: str
    name: Optional[str] = None
    sector: Optional[str] = None

    last: Optional[float] = None
    change_pct: Optional[float] = None

    score: Optional[int] = None
    strength: Optional[str] = None

    rsi: Optional[float] = None
    adx: Optional[float] = None
    ret_12_1m: Optional[float] = None
    ret_6m: Optional[float] = None
    ret_3m: Optional[float] = None
    ret_1m: Optional[float] = None
    ret_1w: Optional[float] = None  # 1-week change

    pct_from_52w_high: Optional[float] = None
    atr_pct: Optional[float] = None
    liquidity: Optional[float] = None
    vol_spike: Optional[float] = None
    pct_today: Optional[float] = None

    buy: Optional[bool] = None
    reason: Optional[str] = None
    source: Optional[str] = None
    stale: Optional[bool] = None

    badges: List[Badge] = []  # breakout, near_uc, etc.

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
