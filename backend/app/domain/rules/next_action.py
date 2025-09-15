from __future__ import annotations
from typing import Any, Dict

def compute_next_action(*, price: float | None, indicators: Dict[str, Any], position: Dict[str, Any]) -> Dict[str, Any]:
    ema_n = indicators.get("ema_slow") or 10
    ema_val = indicators.get("ema_slow_value")
    stop_now = position.get("stop_now")

    code = "HOLD"
    text = "Hold"
    reasons: list[str] = []

    if price is not None and ema_val is not None and price >= ema_val:
        code = "HOLD_TRAIL"
        text = f"Hold (trail stop at ₹{stop_now})" if stop_now else "Hold (trail)"
        reasons.append(f"Close ≥ EMA{ema_n}")
        reasons.append("Momentum intact")

    return {"code": code, "text": text, "reasons": reasons, "refs": {"stop_now": stop_now, "ema_n": ema_n, "ema_value": ema_val}}

def method_pill_for(indicators: Dict[str, Any], _score_row: Dict[str, Any]) -> str:
    return f"EMA{indicators.get('ema_slow') or 10}"
