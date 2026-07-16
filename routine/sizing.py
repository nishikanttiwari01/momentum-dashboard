"""Position sizing and price levels. Pure functions, fully unit-tested."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class TradePlan:
    entry: float
    stop: float
    t1: float
    t2: float
    qty: int
    risk_rupees: float
    position_rupees: float


def round_tick(price: float, tick: float = 0.05) -> float:
    """NSE prices trade in Rs 0.05 ticks."""
    return round(round(price / tick) * tick, 2)


def build_plan(
    close: float,
    atr_pct: float,
    capital: float,
    risk_pct: float,
    stop_atr_mult: float = 2.0,
    t1_gain_pct: float = 10.0,
    t2_gain_pct: float = 20.0,
    pivot: Optional[float] = None,
    size_multiplier: float = 1.0,
) -> Optional[TradePlan]:
    """Entry/stop/targets/qty for a candidate. None if the plan is untradeable.

    Entry: if a pivot sits within 3% above close, use it as the breakout
    trigger; otherwise enter at ~close (next-day limit).
    Stop: entry - stop_atr_mult * ATR. Qty: fixed-fractional risk.
    """
    if close is None or close <= 0 or atr_pct is None or atr_pct <= 0:
        return None
    entry = close
    if pivot is not None and close < pivot <= close * 1.03:
        entry = pivot * 1.001  # trigger just above resistance
    atr_abs = entry * (atr_pct / 100.0)
    stop = entry - stop_atr_mult * atr_abs
    if stop <= 0 or stop >= entry:
        return None
    per_share_risk = entry - stop
    risk_budget = capital * (risk_pct / 100.0) * max(size_multiplier, 0.0)
    if risk_budget <= 0:
        return None
    qty = math.floor(risk_budget / per_share_risk)
    if qty < 1:
        return None
    position = qty * entry
    if position > capital:  # cap position at full capital (no leverage)
        qty = math.floor(capital / entry)
        if qty < 1:
            return None
        position = qty * entry
    return TradePlan(
        entry=round_tick(entry),
        stop=round_tick(stop),
        t1=round_tick(entry * (1 + t1_gain_pct / 100.0)),
        t2=round_tick(entry * (1 + t2_gain_pct / 100.0)),
        qty=qty,
        risk_rupees=round(qty * per_share_risk, 0),
        position_rupees=round(position, 0),
    )
