from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, List, Tuple

from app.core import config as app_config

__all__ = [
    "evaluate_buy_gate",
    "compose_human_reason",
    "get_threshold_float",
    "get_threshold_range",
]

OptionalFloat = float | None


@lru_cache(maxsize=1)
def _alert_thresholds() -> Dict[str, Any]:
    try:
        settings = app_config.get_settings()
        alerts_cfg = getattr(settings, "alerts", {}) or {}
        if hasattr(alerts_cfg, "model_dump"):
            alerts_cfg = alerts_cfg.model_dump()
        thresholds = alerts_cfg.get("thresholds") or {}
        if hasattr(thresholds, "model_dump"):
            thresholds = thresholds.model_dump()
        if isinstance(thresholds, dict):
            return dict(thresholds)
    except Exception:
        pass
    return {}


def _threshold_float(name: str, default: float) -> float:
    values = _alert_thresholds()
    val = values.get(name)
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _threshold_range(name: str, default: Tuple[float, float]) -> Tuple[float, float]:
    values = _alert_thresholds()
    val = values.get(name)
    if isinstance(val, (list, tuple)) and len(val) >= 2:
        lo_raw, hi_raw = val[0], val[1]
        lo = float(lo_raw) if lo_raw is not None else default[0]
        hi = float(hi_raw) if hi_raw is not None else default[1]
        return (lo, hi)
    return default


def _maybe_float(value: Any) -> OptionalFloat:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):  # NaN check
        return None
    return f


def _format_percent(value: OptionalFloat, decimals: int = 1, include_sign: bool = False) -> str:
    if value is None:
        return "NA"
    if include_sign:
        return f"{value:+.{decimals}f}%"
    return f"{value:.{decimals}f}%"


def _format_multiplier(value: OptionalFloat, decimals: int = 1) -> str:
    if value is None:
        return "NA"
    return f"{value:.{decimals}f}x"


def _format_int(value: OptionalFloat) -> str:
    if value is None:
        return "NA"
    return str(int(round(value)))


def _format_liquidity(value: OptionalFloat) -> str:
    if value is None:
        return "NA"
    return f"{value / 1e7:.1f}Cr"


ReasonItem = Tuple[str, str, str]
ReasonMetric = Tuple[str, str, str, bool]


def _compose_reason_string(items: List[ReasonItem]) -> str:
    return " | ".join(f"{label}: {value} ({desc})" for label, value, desc in items if label)


def compose_human_reason(items: List[ReasonItem]) -> str:
    return _compose_reason_string(items)


def _summarize_score(value: Any, minimum: float, label: str = "Score") -> ReasonMetric:
    val = _maybe_float(value)
    if val is None:
        return label, "NA", "score unavailable", False
    value_str = _format_int(val)
    if val >= minimum:
        return label, value_str, "quality met", True
    return label, value_str, "strength low", False


def _summarize_pivot(value: Any, lower: float, upper: float) -> ReasonMetric:
    val = _maybe_float(value)
    if val is None:
        return "pivot_clear", "NA", "pivot data missing", False
    value_str = _format_percent(val, include_sign=True)
    if val < 0:
        desc = "below resistance"
    elif val < lower:
        desc = "testing breakout"
    elif val <= upper:
        desc = "clean breakout"
    else:
        desc = "overextended"
    passed = lower <= val <= upper
    return "pivot_clear", value_str, desc, passed


def _summarize_base_len(value: Any, minimum: float) -> ReasonMetric:
    val = _maybe_float(value)
    if val is None:
        return "base_len", "NA", "base data unavailable", False
    length = int(round(val))
    if length < 10:
        desc = "no clear base"
    elif length < minimum:
        desc = "early consolidation"
    elif length <= 25:
        desc = "ready to break"
    elif length <= 35:
        desc = "extended base"
    else:
        desc = "stale setup"
    passed = length >= minimum
    return "base_len", str(length), desc, passed


def _summarize_relvol(value: Any, minimum: float, label: str = "RelVol") -> ReasonMetric:
    val = _maybe_float(value)
    if val is None:
        return label, "NA", "volume data missing", False
    value_str = _format_multiplier(val)
    if val < 1.0:
        desc = "quiet volume"
    elif val < minimum:
        desc = "average volume"
    elif val <= 2.0:
        desc = "strong buying"
    else:
        desc = "high-volume breakout"
    passed = val >= minimum
    return label, value_str, desc, passed


def _summarize_atr(value: Any, lower: float, upper: float) -> ReasonMetric:
    val = _maybe_float(value)
    if val is None:
        return "ATR10", "NA", "ATR unavailable", False
    value_str = _format_percent(val)
    if val < lower:
        desc = "low volatility"
    elif val <= upper:
        desc = "healthy volatility"
    else:
        desc = "too volatile"
    passed = lower <= val <= upper
    return "ATR10", value_str, desc, passed


def _summarize_adx(value: Any, minimum: float) -> ReasonMetric:
    val = _maybe_float(value)
    if val is None:
        return "ADX", "NA", "trend data missing", False
    value_str = _format_int(val)
    if val < 20:
        desc = "weak trend"
    elif val < minimum:
        desc = "emerging trend"
    elif val <= 35:
        desc = "strong trend"
    else:
        desc = "euphoric trend"
    passed = val >= minimum
    return "ADX", value_str, desc, passed


def _summarize_proximity(value: Any, minimum: float) -> ReasonMetric:
    val = _maybe_float(value)
    if val is None:
        return "prox52", "NA", "proximity unknown", False
    value_str = _format_percent(val, include_sign=True)
    if val < -15:
        desc = "far from highs"
    elif val < minimum:
        desc = "building base"
    elif val <= 0:
        desc = "near breakout zone"
    else:
        desc = "at highs"
    passed = val >= minimum
    return "prox52", value_str, desc, passed


def _summarize_day_change(value: Any, maximum: float, label: str = "day_change") -> ReasonMetric:
    val = _maybe_float(value)
    if val is None:
        return label, "NA", "day change unknown", False
    value_str = _format_percent(val, include_sign=True)
    if val > maximum:
        return label, value_str, "too extended today", False
    if val >= 0:
        return label, value_str, "calm session", True
    return label, value_str, "pullback day", True


def _summarize_liquidity(value: Any, minimum: float) -> ReasonMetric:
    val = _maybe_float(value)
    if val is None:
        return "liquidity", "NA", "liquidity unknown", False
    value_str = _format_liquidity(val)
    if val >= minimum:
        return "liquidity", value_str, "adequate liquidity", True
    return "liquidity", value_str, "thin liquidity", False


def _summarize_rsi(value: Any, lower: float, upper: float) -> ReasonMetric:
    val = _maybe_float(value)
    if val is None:
        return "RSI", "NA", "RSI unavailable", False
    value_str = _format_int(val)
    if val < lower:
        desc = "momentum weak"
    elif val <= upper:
        desc = "bullish momentum"
    else:
        desc = "overbought"
    passed = lower <= val <= upper
    return "RSI", value_str, desc, passed


def _summarize_adx_slope(value: Any) -> ReasonMetric:
    if value is True:
        return "ADX_slope", "+", "trend strength rising", True
    if value is False:
        return "ADX_slope", "flat", "trend not improving", False
    return "ADX_slope", "NA", "trend slope unknown", False


def _summarize_persistence(value: Any) -> ReasonMetric:
    if value is True:
        return "persistence", "Yes", "holding pivot/VWAP", True
    if value is False:
        return "persistence", "No", "lost pivot/VWAP", False
    return "persistence", "NA", "persistence unknown", False


def _build_eod_buy_metrics(row: Dict[str, Any]) -> Tuple[bool, List[ReasonItem]]:
    reason_items: List[ReasonItem] = []
    passed = True

    def add(metric: ReasonMetric, enforce: bool = True) -> None:
        nonlocal passed
        label, value_str, desc, ok = metric
        reason_items.append((label, value_str, desc))
        if enforce:
            passed = passed and bool(ok)

    score_min = _threshold_float("breakout_score_min", 70.0)
    add(_summarize_score(row.get("score"), score_min))

    pivot_lo, pivot_hi = _threshold_range("breakout_pivot_clear_pct_range", (1.0, 5.0))
    add(_summarize_pivot(row.get("pivot_clear_pct"), pivot_lo, pivot_hi))

    base_len_min = _threshold_float("base_len_min_bars", 15.0)
    if base_len_min <= 0:
        base_len_min = 15.0
    add(_summarize_base_len(row.get("base_len_bars"), base_len_min))

    relvol_min = _threshold_float("breakout_relvol20_min", 1.5)
    add(_summarize_relvol(row.get("relvol20"), relvol_min))

    atr_lo, atr_hi = _threshold_range("atr10_pct_range", (3.0, 7.0))
    atr_val = row.get("atr10_pct") if row.get("atr10_pct") is not None else row.get("atr_pct")
    add(_summarize_atr(atr_val, atr_lo, atr_hi))

    adx_min = _threshold_float("adx14_min", 22.0)
    add(_summarize_adx(row.get("adx") or row.get("adx14"), adx_min))

    prox_min = _threshold_float("proximity_52w_min_pct", -8.0)
    prox_val = row.get("pct_from_52w_high") if row.get("pct_from_52w_high") is not None else row.get("proximity_52w_high_pct")
    add(_summarize_proximity(prox_val, prox_min))

    day_cap = _threshold_float("day_change_cap_breakout_pct", 6.0)
    day_val = row.get("change_pct") if row.get("change_pct") is not None else row.get("pct_today")
    add(_summarize_day_change(day_val, day_cap))

    liquidity_floor = _threshold_float("liquidity_floor_rupees", 5e7)
    liquidity_val = row.get("liquidity")
    if liquidity_val is None:
        liquidity_val = row.get("median_traded_value_20d")
    add(_summarize_liquidity(liquidity_val, liquidity_floor))

    return passed, reason_items


def _build_intraday_buy_metrics(row: Dict[str, Any]) -> Tuple[bool, List[ReasonItem]]:
    reason_items: List[ReasonItem] = []
    passed = True

    def add(metric: ReasonMetric, enforce: bool = True) -> None:
        nonlocal passed
        label, value_str, desc, ok = metric
        reason_items.append((label, value_str, desc))
        if enforce:
            passed = passed and bool(ok)

    score_min = _threshold_float("breakout_score_min", 70.0)
    add(_summarize_score(row.get("score"), score_min), enforce=False)

    pivot_lo, pivot_hi = _threshold_range("breakout_pivot_clear_pct_range", (1.0, 5.0))
    add(_summarize_pivot(row.get("pivot_clear_pct"), pivot_lo, pivot_hi), enforce=False)

    base_len_min = _threshold_float("base_len_min_bars", 15.0)
    if base_len_min <= 0:
        base_len_min = 15.0
    add(_summarize_base_len(row.get("base_len_bars"), base_len_min), enforce=False)

    starter_score_min = _threshold_float("starter_score_min_intraday", 65.0)
    intraday_score = row.get("intraday_score")
    if intraday_score is None:
        intraday_score = row.get("score")
    add(_summarize_score(intraday_score, starter_score_min, label="starter_score"))

    relvol_source = row.get("intraday_relvol")
    if relvol_source is None:
        relvol_source = row.get("relvol20") if row.get("relvol20") is not None else row.get("vol_spike")
    relvol_min = _threshold_float("intraday_relvol_min", 1.5)
    add(_summarize_relvol(relvol_source, relvol_min))

    adx_min = _threshold_float("adx14_min", 22.0)
    add(_summarize_adx(row.get("adx") or row.get("adx14"), adx_min))

    add(_summarize_adx_slope(row.get("adx_slope_pos")))

    add(_summarize_rsi(row.get("rsi") or row.get("rsi14"), 58.0, 70.0))

    prox_min = _threshold_float("proximity_52w_min_pct", -8.0)
    prox_val = row.get("pct_from_52w_high") if row.get("pct_from_52w_high") is not None else row.get("proximity_52w_high_pct")
    add(_summarize_proximity(prox_val, prox_min))

    atr_lo, atr_hi = _threshold_range("atr10_pct_range", (3.0, 7.0))
    atr_val = row.get("atr10_pct") if row.get("atr10_pct") is not None else row.get("atr_pct")
    add(_summarize_atr(atr_val, atr_lo, atr_hi))

    day_cap = _threshold_float("day_change_cap_starter_pct", 4.0)
    day_val = row.get("change_pct") if row.get("change_pct") is not None else row.get("pct_today")
    add(_summarize_day_change(day_val, day_cap))

    liquidity_floor = _threshold_float("liquidity_floor_rupees", 5e7)
    liquidity_val = row.get("liquidity")
    if liquidity_val is None:
        liquidity_val = row.get("median_traded_value_20d")
    add(_summarize_liquidity(liquidity_val, liquidity_floor))

    add(_summarize_persistence(row.get("persistence_ok")))

    return passed, reason_items


def get_threshold_float(name: str, default: float) -> float:
    return _threshold_float(name, default)


def get_threshold_range(name: str, default: Tuple[float, float]) -> Tuple[float, float]:
    return _threshold_range(name, default)


def evaluate_buy_gate(row: Dict[str, Any]) -> Tuple[str, str]:
    is_eod = bool(row.get("is_eod"))
    row["buy_mode"] = "EOD" if is_eod else "INTRADAY"
    passed, items = _build_eod_buy_metrics(row) if is_eod else _build_intraday_buy_metrics(row)
    reason = compose_human_reason(items)
    return ("Yes" if passed else "No"), reason
