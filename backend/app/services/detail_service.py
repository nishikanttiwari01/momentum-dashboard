from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.repos.parquet.scores_repo import ScoresRepo
# Create this minimal repo if you don't have it yet (read_one only).
from app.repos.parquet.indicators_repo import IndicatorsRepo
from app.repos.sql.positions_repo import PositionsRepo
from app.repos.sql.snapshot_pins_repo import SnapshotPinsRepo

from app.domain.meters import compute_meters
from app.domain.next_action import compute_next_action, method_pill_for


@dataclass(frozen=True)
class DetailDeps:
    scores: ScoresRepo
    indicators: IndicatorsRepo
    positions: PositionsRepo
    pins: SnapshotPinsRepo


def _resolve_run_id(symbol: str, explicit: Optional[str], deps: DetailDeps) -> tuple[str, Optional[str]]:
    """
    Order: explicit run_id > pinned(symbol) > latest
    Returns (run_id, as_of)
    """
    if explicit:
        rid, as_of = explicit, None
    else:
        pinned = deps.pins.get(symbol) if hasattr(deps.pins, "get") else None
        if pinned:
            rid, as_of = pinned, None
        else:
            # Implement latest_run() in ScoresRepo (wrapper on datasets.latest_snapshot)
            rid, as_of = deps.scores.latest_run()
    if not rid:
        raise KeyError("snapshot_not_found")
    return rid, as_of


def build_drawer_detail(symbol: str, run_id: Optional[str], deps: DetailDeps) -> Dict[str, Any]:
    rid, as_of = _resolve_run_id(symbol, run_id, deps)

    score_row = deps.scores.read_one(symbol=symbol, run_id=rid) or {}
    ind_row = deps.indicators.read_one(symbol=symbol, run_id=rid) or {}
    pos = deps.positions.get(symbol) or {}

    price = score_row.get("last")
    pct_today = score_row.get("pct_today") or score_row.get("change_pct")
    score = score_row.get("score")
    name = score_row.get("name")
    sector = score_row.get("sector")
    badges = score_row.get("badges") or []

    # Position: entry price rules
    entry_price = pos.get("entry_price")
    entry_locked = pos.get("entry_price_locked")
    qty = pos.get("qty")
    trade_on = pos.get("trade_on", (qty or 0) > 0)
    calc_entry = entry_locked or entry_price or price

    meters = compute_meters(indicators=ind_row, score_row=score_row)
    next_action = compute_next_action(price=price, indicators=ind_row,
                                      position={**pos, "calc_entry": calc_entry})
    pill = method_pill_for(ind_row, score_row)

    # Phase 8: normalize score for drawer (keep original score for back-compat)
    score_total_0_100 = None
    if score is not None:
        try:
            s = float(score)
            score_total_0_100 = int(round(s * 100)) if s <= 1.0 else int(round(s))
        except Exception:
            score_total_0_100 = None

    return {
        "run_id": rid,
        "as_of": as_of,
        "symbol": symbol,
        "symbol_canon": symbol.upper(),  # canonical form
        "name": name,
        "sector": sector,
        "price": price,
        "pct_today": pct_today,
        "score": score,
        "score_total_0_100": score_total_0_100,
        "indicators": {
            "rsi14": ind_row.get("rsi14"),
            "adx14": ind_row.get("adx14"),
            "adx_slope": ind_row.get("adx_slope"),
            "ema_fast": ind_row.get("ema_fast"),
            "ema_fast_value": ind_row.get("ema_fast_value"),
            "ema_slow": ind_row.get("ema_slow"),
            "ema_slow_value": ind_row.get("ema_slow_value"),
            "relvol20": ind_row.get("relvol20"),
            "proximity_52w_high_pct": score_row.get("proximity_52w_high_pct"),
        },
        "badges": badges,
        "position": {
            "entry_price": entry_price,
            "entry_price_locked": entry_locked,
            "qty": qty,
            "trade_on": trade_on,
            "stop_now": pos.get("stop_now"),
            "exit_close_threshold": pos.get("exit_close_threshold"),
            "breakeven_active": pos.get("breakeven_active"),
            "euphoria_on": pos.get("euphoria_on"),
            "note": pos.get("note"),
        },
        "method_pill": pill,
        "meters": meters,
        "next_action": next_action,
        "alert_templates": [
            {"code": "price_crosses",    "example": "price crosses ₹4050"},
            {"code": "enters_breakout",  "example": "enters breakout"},
            {"code": "close_below_ema",  "example": f"close < EMAₙ ({ind_row.get('ema_slow_value')})"},
            {"code": "breakeven_active", "example": "breakeven active"},
            {"code": "stop_hit",         "example": "stop hit"},
        ],
        "channels": {
            "email":   {"enabled": True,  "sound": False},
            "desktop": {"enabled": True,  "sound": True},
            "whatsapp":{"enabled": False},
        },
    }
