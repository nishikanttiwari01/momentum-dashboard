from __future__ import annotations
from typing import Any, Dict

def compute_meters(*, indicators: Dict[str, Any], score_row: Dict[str, Any]) -> Dict[str, Any]:
    atr = score_row.get("atr_pct")
    risk = "Low"
    if atr is not None:
        if atr >= 3.0:
            risk = "High"
        elif atr >= 1.5:
            risk = "Medium"

    rsi = indicators.get("rsi14")
    adx = indicators.get("adx14") or 0.0
    euphoria = "Low"
    if rsi is not None:
        if rsi >= 70 and adx >= 20:
            euphoria = "High"
        elif rsi >= 60:
            euphoria = "Medium"

    return {
        "risk":     {"level": risk,     "basis": {"atr_pct": atr}},
        "euphoria": {"level": euphoria, "basis": {"rsi14": rsi, "adx14": adx}},
    }
