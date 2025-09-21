from __future__ import annotations
from typing import Any, Dict

def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def compute_meters(*, indicators: Dict[str, Any], score_row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Returns calibrated meters with both categorical levels and 0–100 scores.

    Risk:
      - Based on ATR14% (primary). Higher ATR% => higher risk.
      - Calibration: 0 at 0%, 100 at 8%+ (clamped).
      - Labels: Low  (0–33), Medium (33–66), High (66–100)

    Euphoria:
      - Based on RSI/ADX/ADX slope composite.
      - RSI part: 55→0 up to 80→70 points (clamped 0–70)
      - ADX part: 20→0 up to 45→30 points (clamped 0–30)
      - +5 pts bonus if adx_slope_5 > 0 (clamped overall to 100)
      - Labels: Low  (0–33), Medium (33–66), High (66–100)
    """
    # ---------- Inputs ----------
    # Prefer 'atr14_pct'; keep alias to be defensive/compatible
    atr14 = score_row.get("atr14_pct")
    if atr14 is None:
        # legacy alias in some places
        atr14 = score_row.get("atr_pct")

    rsi = indicators.get("rsi14")
    adx = indicators.get("adx14")
    adx_slope_5 = indicators.get("adx_slope_5")

    # Optional context that FE may want to show in basis
    gap_up_pct = indicators.get("gap_up_pct") if "gap_up_pct" in indicators else score_row.get("gap_up_pct")
    close_pos_in_bar = indicators.get("close_pos_in_bar") if "close_pos_in_bar" in indicators else score_row.get("close_pos_in_bar")

    # ---------- Risk score (0–100, higher = riskier) ----------
    # 0 at 0% ATR; 100 at 8%+ ATR
    if atr14 is None:
        risk_score = None
    else:
        risk_score = int(round(_clamp((float(atr14) / 8.0) * 100.0, 0.0, 100.0)))

    # Labels from score
    def _risk_level(s: int | None) -> str:
        if s is None:
            return "Low"
        if s >= 66:
            return "High"
        if s >= 33:
            return "Medium"
        return "Low"

    risk_level = _risk_level(risk_score)

    # ---------- Euphoria score (0–100, higher = hotter) ----------
    # Compose from RSI and ADX with small slope bonus
    if rsi is None or adx is None:
        euph_score = None
    else:
        # RSI contribution: map 55→0 to 80→70
        rsi_part = _clamp(((float(rsi) - 55.0) / (80.0 - 55.0)) * 70.0, 0.0, 70.0)
        # ADX contribution: map 20→0 to 45→30
        adx_part = _clamp(((float(adx) - 20.0) / (45.0 - 20.0)) * 30.0, 0.0, 30.0)
        slope_bonus = 5.0 if (adx_slope_5 or 0) > 0 else 0.0
        euph_score = int(round(_clamp(rsi_part + adx_part + slope_bonus, 0.0, 100.0)))

    def _euph_level(s: int | None) -> str:
        if s is None:
            # Be conservative: not hot if unknown
            return "Low"
        if s >= 66:
            return "High"
        if s >= 33:
            return "Medium"
        return "Low"

    euph_level = _euph_level(euph_score)

    # ---------- Output ----------
    return {
        "risk": {
            "level": risk_level,
            "score_0_100": risk_score,
            "basis": {
                "atr14_pct": atr14,
                "atr_pct": atr14,  # alias for compatibility with any legacy reader
                "gap_up_pct": gap_up_pct,
                "close_pos_in_bar": close_pos_in_bar,
            },
            "thresholds": {  # FE can render legends consistently
                "low_lt": 33,
                "medium_gte": 33,
                "high_gte": 66
            }
        },
        "euphoria": {
            "level": euph_level,
            "score_0_100": euph_score,
            "basis": {
                "rsi14": rsi,
                "adx14": adx,
                "adx_slope_5": adx_slope_5
            },
            "thresholds": {
                "low_lt": 33,
                "medium_gte": 33,
                "high_gte": 66
            }
        }
    }
