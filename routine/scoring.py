# Copied verbatim from backend/app/domain/scoring.py (compute_score + PBSS reference).
# Vectorized PBSS for backtests lives in routine/pbss.py (proven equivalent by tests).

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

import math


ScoreDict = Dict[str, float]


@dataclass
class ScoreComponents:
    proximity: float = 0.0
    returns: float = 0.0
    accumulation: float = 0.0
    trend: float = 0.0
    context: float = 0.0
    delivery_bonus: float = 0.0
    penalties: Dict[str, float] = field(default_factory=dict)

    def total_base(self) -> float:
        return self.proximity + self.returns + self.accumulation + self.trend

    def total_with_context(self) -> float:
        return self.total_base() + self.context + self.delivery_bonus


@dataclass
class ScoreBundle:
    score_full: Optional[int]
    score_basic: Optional[int]
    badges: List[Dict[str, str]]
    components: ScoreComponents
    reason_codes: List[str]
    band: str


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _points_proximity(proximity_pct: Optional[float]) -> float:
    """0-20 pts. Rewards stocks near or at 52-week highs (momentum sweet spot)."""
    if proximity_pct is None:
        return 0.0
    p = float(proximity_pct)
    if p >= 0:
        return 20.0
    if p >= -3:
        return 17.0 + ((p + 3.0) / 3.0) * 3.0
    if p >= -8:
        return 11.0 + ((p + 8.0) / 5.0) * 6.0
    if p >= -15:
        return 4.0 + ((p + 15.0) / 7.0) * 7.0
    if p >= -25:
        return ((p + 25.0) / 10.0) * 4.0
    return 0.0


def _points_returns(ret_5d: Optional[float], ret_1m: Optional[float], ret_3m: Optional[float] = None) -> float:
    """0-20 pts. Rewards recent multi-timeframe momentum (key for monthly income goal)."""
    total = 0.0
    if ret_5d is not None:
        r5 = float(ret_5d)
        if r5 >= 5.0:
            total += 8.0
        elif r5 >= 3.0:
            total += 5.0
        elif r5 >= 1.0:
            total += 2.0
    if ret_1m is not None:
        r1m = float(ret_1m)
        if r1m >= 10.0:
            total += 7.0
        elif r1m >= 6.0:
            total += 4.0
        elif r1m >= 2.0:
            total += 1.0
    if ret_3m is not None:
        r3m = float(ret_3m)
        if r3m >= 20.0:
            total += 5.0
        elif r3m >= 12.0:
            total += 3.0
        elif r3m >= 5.0:
            total += 1.0
    return min(total, 20.0)


def _points_accumulation(relvol20: Optional[float], vol_z20: Optional[float], obv_above_ma: Optional[bool], obv_slope_10: Optional[float]) -> float:
    """0-15 pts. Rewards institutional-style accumulation via volume and OBV."""
    total = 0.0
    if relvol20 is not None:
        rv = float(relvol20)
        if rv >= 2.0:
            total += 5.0
        elif rv >= 1.5:
            total += 3.0
        elif rv >= 1.2:
            total += 1.0
    if vol_z20 is not None:
        vz = float(vol_z20)
        if vz >= 2.0:
            total += 3.0
        elif vz >= 1.0:
            total += 2.0
        elif vz >= 0.5:
            total += 1.0
    if obv_above_ma:
        total += 4.0
    if obv_slope_10 is not None and float(obv_slope_10) > 0.0:
        total += 3.0
    return min(total, 15.0)


def _points_structure(close: Optional[float], ema10: Optional[float], ema50: Optional[float], ema200: Optional[float]) -> float:
    """0-16 pts. EMA alignment — necessary condition but not the dominant factor."""
    pts = 0.0
    if close is not None and ema50 is not None:
        if close >= ema50:
            pts += 8.0
        elif close >= (ema10 or ema50):
            pts += 4.0
    if ema10 is not None and ema50 is not None and ema10 > ema50:
        pts += 4.0
    if ema50 is not None and ema200 is not None and ema50 > ema200:
        pts += 4.0
    return min(pts, 16.0)


def _points_rsi(rsi14: Optional[float]) -> float:
    """0-10 pts. RSI 60-75 is the momentum sweet spot for Indian breakouts."""
    if rsi14 is None:
        return 0.0
    r = float(rsi14)
    if r < 50.0:
        return 0.0
    if r < 55.0:
        return 10.0 * 0.35
    if r < 60.0:
        return 10.0 * 0.60
    if r < 65.0:
        return 10.0 * 0.80
    if r < 70.0:
        return 10.0 * 0.95
    if r < 75.0:
        return 10.0
    if r < 80.0:
        return 10.0 * 0.85
    return 10.0 * 0.70


def _points_adx(adx14: Optional[float], adx_slope_pos: Optional[bool]) -> float:
    """0-12 pts. ADX confirms trend strength; slope confirms acceleration."""
    if adx14 is None:
        return 0.0
    a = float(adx14)
    if a < 20.0:
        pts = 0.0
    elif a < 25.0:
        pts = 12.0 * 0.40
    elif a < 30.0:
        pts = 12.0 * 0.60
    elif a < 35.0:
        pts = 12.0 * 0.80
    elif a < 45.0:
        pts = 12.0 * 0.92
    else:
        pts = 12.0
    if adx_slope_pos:
        pts = min(pts + 2.0, 12.0)
    return pts


def _points_trend(close: Optional[float], ema10: Optional[float], ema50: Optional[float], ema200: Optional[float],
                  rsi14: Optional[float], adx14: Optional[float], adx_slope_pos: Optional[bool],
                  mansfield_rs_52: Optional[float]) -> float:
    """0-40 pts total (structure 16 + RSI 10 + ADX 12 + Mansfield 4)."""
    structure = _points_structure(close, ema10, ema50, ema200)
    rsi_pts = _points_rsi(rsi14)
    adx_pts = _points_adx(adx14, adx_slope_pos)
    mansfield_bonus = 0.0
    if mansfield_rs_52 is not None:
        if mansfield_rs_52 >= 0.0:
            mansfield_bonus = min(4.0, mansfield_rs_52 * 4.0)
        else:
            mansfield_bonus = max(-2.0, mansfield_rs_52 * 2.0)
    total = structure + rsi_pts + adx_pts + mansfield_bonus
    return _clamp(total, 0.0, 40.0)


def _context_bonus(nifty_regime: Optional[str], breadth_pct_50dma: Optional[float], delivery_ratio_20d: Optional[float]) -> Tuple[float, Dict[str, float]]:
    bonus = 0.0
    parts: Dict[str, float] = {}
    regime = (nifty_regime or "").upper()
    if regime == "UP":
        parts["regime"] = 2.0
    elif regime == "NEUTRAL":
        parts["regime"] = 1.0
    else:
        parts["regime"] = 0.0
    breadth = _safe_float(breadth_pct_50dma)
    if breadth is not None:
        if breadth >= 55.0:
            parts["breadth"] = 2.0
        elif breadth >= 45.0:
            parts["breadth"] = 1.0
        else:
            parts["breadth"] = 0.0
    delivery = _safe_float(delivery_ratio_20d)
    if delivery is not None and delivery >= 0.45:
        parts["delivery"] = 1.0
    bonus = sum(parts.values())
    bonus = min(bonus, 5.0)
    return bonus, parts


def _penalties(rsi14: Optional[float], gap_up_pct: Optional[float], close_pos_in_bar: Optional[float],
               pivot_clear_pct: Optional[float], n_consecutive_up: Optional[float]) -> Dict[str, float]:
    penalties: Dict[str, float] = {}
    r = _safe_float(rsi14)
    if r is not None and r > 80.0:
        penalties["rsi_over_80"] = -3.0

    gap = _safe_float(gap_up_pct)
    close_pos = _safe_float(close_pos_in_bar)
    if gap is not None and close_pos is not None and gap > 4.0 and close_pos < 0.5:
        if gap >= 8.0 and close_pos < 0.3:
            penalties["gap_weak_close"] = -5.0
        elif gap >= 6.0 and close_pos < 0.4:
            penalties["gap_weak_close"] = -3.0
        else:
            penalties["gap_weak_close"] = -2.0

    pivot_clear = _safe_float(pivot_clear_pct)
    n_up = _safe_float(n_consecutive_up)
    if pivot_clear is not None and pivot_clear > 5.0:
        if pivot_clear > 12.0:
            penalties["late_breakout"] = -6.0
        elif pivot_clear > 8.0:
            penalties["late_breakout"] = -4.0
        else:
            penalties["late_breakout"] = -2.0
    if n_up is not None and n_up >= 4:
        penalties.setdefault("late_breakout", -2.0)

    return penalties


def _band_for_score(score: Optional[int]) -> str:
    if score is None:
        return "UNKNOWN"
    if score <= 40:
        return "IGNORE"
    if score <= 55:
        return "WATCH"
    if score <= 69:
        return "HIGH"
    if score <= 78:
        return "BREAKOUT"
    return "ELITE"


def _band_badge(score_band: str) -> Dict[str, str]:
    labels = {
        "IGNORE": "Ignore",
        "WATCH": "Watch",
        "HIGH": "High Potential",
        "BREAKOUT": "Breakout Zone",
        "ELITE": "Elite Momentum",
        "UNKNOWN": "Incomplete",
    }
    category = "BAND"
    return {"category": category, "label": labels.get(score_band, "Incomplete")}


def _build_badges(score_band: str, components: ScoreComponents) -> List[Dict[str, str]]:
    badges: List[Dict[str, str]] = [_band_badge(score_band)]
    if components.proximity >= 10.0:
        badges.append({"category": "PRICE", "label": "Near 52W High"})
    if components.accumulation >= 5.0:
        badges.append({"category": "VOLUME", "label": "Accumulation"})
    if components.trend >= 50.0:
        badges.append({"category": "TREND", "label": "Strong Trend"})
    if components.returns >= 6.0:
        badges.append({"category": "MOMENTUM", "label": "Hot Returns"})
    return badges


def _reason_codes(components: ScoreComponents, penalties: Dict[str, float], extras: Dict[str, Any]) -> List[str]:
    codes: List[str] = []
    prox = extras.get("proximity_52w_high_pct")
    if prox is not None:
        codes.append(f"prox52:{float(prox):.1f}%")
    relvol = extras.get("relvol20")
    if relvol is not None:
        codes.append(f"RelVol:{float(relvol):.1f}x")
    adx = extras.get("adx14")
    if adx is not None:
        slope = extras.get("adx_slope_pos")
        arrow = "↑" if slope else ""
        codes.append(f"ADX:{float(adx):.0f}{arrow}")
    n_up = extras.get("n_consecutive_up")
    if n_up is not None:
        codes.append(f"3up:{int(n_up)}")
    pivot_clear = extras.get("pivot_clear_pct")
    if pivot_clear is not None:
        codes.append(f"pivot_clear:{float(pivot_clear):.1f}%")
    if penalties:
        for key, val in penalties.items():
            codes.append(f"penalty:{key}:{int(val)}")
    return codes


def compute_score(inputs: Dict[str, Any]) -> ScoreBundle:
    prox_points = _points_proximity(_safe_float(inputs.get("proximity_52w_high_pct")))
    returns_points = _points_returns(
        _safe_float(inputs.get("ret_5d") or inputs.get("ret_1w")),
        _safe_float(inputs.get("ret_1m")),
        _safe_float(inputs.get("ret_3m")),
    )
    accumulation_points = _points_accumulation(
        _safe_float(inputs.get("relvol20")),
        _safe_float(inputs.get("vol_z20")),
        bool(inputs.get("obv_above_ma")),
        _safe_float(inputs.get("obv_slope_10")),
    )
    trend_points = _points_trend(
        _safe_float(inputs.get("close") or inputs.get("last")),
        _safe_float(inputs.get("ema10")),
        _safe_float(inputs.get("ema50")),
        _safe_float(inputs.get("ema200")),
        _safe_float(inputs.get("rsi14") or inputs.get("rsi")),
        _safe_float(inputs.get("adx14") or inputs.get("adx")),
        bool(inputs.get("adx_slope_pos")),
        _safe_float(inputs.get("mansfield_rs_52")),
    )

    context_bonus, context_parts = _context_bonus(
        inputs.get("nifty_regime"),
        _safe_float(inputs.get("breadth_pct_50dma")),
        _safe_float(inputs.get("delivery_ratio_20d")),
    )
    penalties = _penalties(
        _safe_float(inputs.get("rsi14") or inputs.get("rsi")),
        _safe_float(inputs.get("gap_up_pct")),
        _safe_float(inputs.get("close_pos_in_bar")),
        _safe_float(inputs.get("pivot_clear_pct")),
        _safe_float(inputs.get("n_consecutive_up")),
    )
    delivery_bonus = context_parts.get("delivery", 0.0)
    context_without_delivery = context_bonus - delivery_bonus
    if context_without_delivery < 0:
        context_without_delivery = 0.0

    components = ScoreComponents(
        proximity=prox_points,
        returns=returns_points,
        accumulation=accumulation_points,
        trend=trend_points,
        context=context_without_delivery,
        delivery_bonus=delivery_bonus,
        penalties=penalties,
    )

    full_ready_fields = (
        inputs.get("proximity_52w_high_pct") is not None
        and inputs.get("relvol20") is not None
        and inputs.get("vol_z20") is not None
        and inputs.get("obv_above_ma") is not None
        and inputs.get("obv_slope_10") is not None
        and inputs.get("ema50") is not None
        and inputs.get("ema200") is not None
        and inputs.get("adx14") is not None
        and inputs.get("rsi14") is not None
    )

    base_total = components.total_base()
    full_total = components.total_with_context()
    penalty_total = sum(penalties.values())
    full_score_val = full_total + penalty_total
    full_score = int(round(_clamp(full_score_val, 0.0, 100.0))) if full_ready_fields else None

    # Basic score: scale base_total to 0-100 ignoring context/penalties.
    # Max base = proximity(20) + returns(20) + accumulation(15) + trend(40) = 95.
    basic_score = int(round(_clamp((base_total / 95.0) * 100.0, 0.0, 100.0))) if base_total > 0 else 0

    band = _band_for_score(full_score if full_score is not None else basic_score)
    badges = _build_badges(band, components)

    reason_codes = _reason_codes(components, penalties, inputs)
    return ScoreBundle(
        score_full=full_score,
        score_basic=basic_score,
        badges=badges,
        components=components,
        reason_codes=reason_codes,
        band=band,
    )


# ---------------------------------------------------------------------------
# Pre-Breakout Surge Score (PBSS)
# ---------------------------------------------------------------------------
# A composite early-warning score that identifies stocks showing institutional
# accumulation signatures 20-30 days BEFORE a significant price surge.
#
# Derived from backtesting 400+ trading days of NSE parquet snapshots:
#   PBSS  0-8:  1-2.7% surge rate (baseline)
#   PBSS 12:    7.7% surge rate, avg ret_1m +6.1%
#   PBSS 16:   11.7% surge rate, avg ret_1m +8.4%
#   PBSS 18:   15.9% surge rate, avg ret_1m +10.2%
#   PBSS 20:   43.8% surge rate, avg ret_1m +19.8%   ← strong institutional signal
#
# Alert thresholds recommended:
#   >= 12: Add to candidate pool / watchlist (pre-breakout radar)
#   >= 16: WATCHLIST_ALERT — monitor closely, volume accumulation confirmed
#   >= 20: SURGE_ALERT — high-conviction pre-breakout (43% chance of 25%+ gain)
#
# Inputs use the same dict as compute_score() for full compatibility.
# ---------------------------------------------------------------------------

@dataclass
class PreBreakoutBundle:
    pbss: int
    components: Dict[str, float]
    alert_level: str   # "NONE" | "WATCHLIST" | "SURGE"
    reason: str


def compute_pre_breakout_score(inputs: Dict[str, Any]) -> PreBreakoutBundle:
    """Compute the Pre-Breakout Surge Score (PBSS) from a screener row dict.

    Weights derived statistically: vol_z20 is the single most predictive
    factor (20x lift vs baseline), followed by ret_5d kick and relvol.
    """
    pts: Dict[str, float] = {}

    # 1. Volume Z-score vs 20-day mean (most predictive — 20x lift)
    vol_z = _safe_float(inputs.get("vol_z20"))
    if vol_z is not None:
        if vol_z >= 3.0:
            pts["vol_z20"] = 4.0
        elif vol_z >= 2.0:
            pts["vol_z20"] = 3.0
        elif vol_z >= 1.5:
            pts["vol_z20"] = 2.0
        elif vol_z >= 1.0:
            pts["vol_z20"] = 1.0

    # 2. Relative volume vs own 20-day average (2.77x lift at >=2x)
    relvol = _safe_float(inputs.get("relvol20"))
    if relvol is not None:
        if relvol >= 2.5:
            pts["relvol"] = 3.0
        elif relvol >= 1.8:
            pts["relvol"] = 2.0
        elif relvol >= 1.3:
            pts["relvol"] = 1.0

    # 3. OBV accumulation — dark-pool / institutional buying invisible to price
    if inputs.get("obv_above_ma"):
        pts["obv_above_ma"] = 2.0
    obv_slope = _safe_float(inputs.get("obv_slope_10"))
    if obv_slope is not None and obv_slope > 0:
        pts["obv_slope"] = 1.0

    # 4. Momentum kick — ret_5d shows the move has already started (2.93x lift)
    ret_5d = _safe_float(inputs.get("ret_5d") or inputs.get("ret_1w"))
    if ret_5d is not None:
        if ret_5d >= 8.0:
            pts["ret_5d"] = 3.0
        elif ret_5d >= 5.0:
            pts["ret_5d"] = 2.0
        elif ret_5d >= 3.0:
            pts["ret_5d"] = 1.0

    # 5. Overall model score (2.63x lift at score >= 65)
    score = _safe_float(inputs.get("score") or inputs.get("score_full"))
    if score is not None:
        if score >= 70:
            pts["score"] = 2.0
        elif score >= 60:
            pts["score"] = 1.0

    # 6. Trend confirmation (ADX + RSI sweet spot 50-72)
    adx = _safe_float(inputs.get("adx14") or inputs.get("adx"))
    if adx is not None and adx >= 30:
        pts["adx"] = 1.0
    rsi = _safe_float(inputs.get("rsi14") or inputs.get("rsi"))
    if rsi is not None and 50.0 <= rsi <= 72.0:
        pts["rsi_sweet_spot"] = 1.0

    # 7. Price proximity to 52W high (within striking distance → breakout imminent)
    prox52 = _safe_float(inputs.get("proximity_52w_high_pct") or inputs.get("pct_from_52w_high"))
    if prox52 is not None:
        if -8.0 <= prox52 <= 2.0:
            pts["prox52"] = 2.0
        elif -15.0 <= prox52 < -8.0:
            pts["prox52"] = 1.0

    # 8. Pivot clear — stock approaching or just above resistance
    pivot = _safe_float(inputs.get("pivot_clear_pct"))
    if pivot is not None:
        if -2.0 <= pivot <= 5.0:
            pts["pivot_near"] = 2.0
        elif -5.0 <= pivot < -2.0:
            pts["pivot_near"] = 1.0

    # 9. Consecutive up days (trend persistence)
    n_up = _safe_float(inputs.get("n_consecutive_up"))
    if n_up is not None and n_up >= 3:
        pts["n_consec_up"] = 1.0

    total = int(round(sum(pts.values())))

    if total >= 20:
        level = "SURGE"
        reason = f"PBSS={total}: High-conviction pre-breakout. Vol surge (z={vol_z:.1f}), relvol={relvol:.1f}x, ret5d={ret_5d:.1f}%. Est. 44% prob of 25%+ gain in 1 month."
    elif total >= 16:
        level = "WATCHLIST"
        reason = f"PBSS={total}: Volume accumulation confirmed. Monitor for entry trigger (relvol {relvol:.1f}x, vol_z {vol_z:.1f})."
    elif total >= 12:
        level = "RADAR"
        reason = f"PBSS={total}: Early accumulation signals. Add to pre-breakout radar."
    else:
        level = "NONE"
        reason = f"PBSS={total}"

    return PreBreakoutBundle(pbss=total, components=pts, alert_level=level, reason=reason)
