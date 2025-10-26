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


def _comparison_symbols(comparator: str) -> Tuple[str, str]:
    if comparator == "ge":
        return "≥", "<"
    if comparator == "le":
        return "≤", ">"
    raise ValueError(f"Unsupported comparator '{comparator}'")


def _format_threshold_display(
    value_display: str,
    rule_display: str,
    *,
    passed: bool,
    comparator: str,
) -> Tuple[str, str]:
    pass_symbol, fail_symbol = _comparison_symbols(comparator)
    if value_display == "NA":
        return "NA", f"{pass_symbol} {rule_display}"
    symbol = pass_symbol if passed else fail_symbol
    return f"{value_display} {symbol} {rule_display}", f"{pass_symbol} {rule_display}"


def _format_range_display(
    value_display: str,
    lower_value: OptionalFloat,
    upper_value: OptionalFloat,
    lower_display: str,
    upper_display: str,
    *,
    passed: bool,
    raw_value: OptionalFloat,
) -> Tuple[str, str]:
    rule_display = f"in {lower_display}...{upper_display}"
    if value_display == "NA":
        return "NA", rule_display
    if passed or raw_value is None or lower_value is None or upper_value is None:
        return f"{value_display} in {lower_display}...{upper_display}", rule_display
    try:
        raw = float(raw_value)
    except (TypeError, ValueError):
        return f"{value_display} in {lower_display}...{upper_display}", rule_display
    if raw < lower_value:
        return f"{value_display} < {lower_display}", rule_display
    if raw > upper_value:
        return f"{value_display} > {upper_display}", rule_display
    return f"{value_display} in {lower_display}...{upper_display}", rule_display


def _format_boolean_display(
    value_display: str,
    rule_display: str,
    *,
    passed: bool,
) -> Tuple[str, str]:
    if value_display == "NA":
        return "NA", rule_display
    comparator = "matches" if passed else "≠"
    return f"{value_display} {comparator} {rule_display}", rule_display


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


def _build_eod_buy_metrics(row: Dict[str, Any]) -> Tuple[bool, List[ReasonItem], List[Dict[str, Any]]]:
    reason_items: List[ReasonItem] = []
    checklist_items: List[Dict[str, Any]] = []
    passed = True

    def add(
        metric: ReasonMetric,
        *,
        enforce: bool = True,
        code: str | None = None,
        label_override: str | None = None,
        value_vs_rule: str | None = None,
        rule_display: str | None = None,
    ) -> None:
        nonlocal passed
        label, value_str, desc, ok = metric
        factor_label = label_override or label.replace("_", " ").title()
        metric_code = code or label
        reason_items.append((factor_label, value_str, desc))
        checklist_items.append(
            {
                "code": metric_code,
                "factor": factor_label,
                "value_display": value_str,
                "value_vs_rule": value_vs_rule or value_str,
                "rule_display": rule_display,
                "description": desc,
                "passed": bool(ok),
                "enforced": bool(enforce),
            }
        )
        if enforce:
            passed = passed and bool(ok)

    score_min = _threshold_float("breakout_score_min", 70.0)
    score_metric = _summarize_score(row.get("score"), score_min)
    score_rule_value = _format_int(score_min)
    score_vr, score_rule_disp = _format_threshold_display(
        score_metric[1], score_rule_value, passed=score_metric[3], comparator="ge"
    )
    add(
        score_metric,
        code="score",
        label_override="Score",
        value_vs_rule=score_vr,
        rule_display=score_rule_disp,
    )

    pivot_lo, pivot_hi = _threshold_range("breakout_pivot_clear_pct_range", (1.0, 5.0))
    pivot_val = _maybe_float(row.get("pivot_clear_pct"))
    pivot_metric = _summarize_pivot(pivot_val, pivot_lo, pivot_hi)
    pivot_vr, pivot_rule_disp = _format_range_display(
        pivot_metric[1],
        pivot_lo,
        pivot_hi,
        _format_percent(pivot_lo, include_sign=True),
        _format_percent(pivot_hi, include_sign=True),
        passed=pivot_metric[3],
        raw_value=pivot_val,
    )
    add(
        pivot_metric,
        code="pivot_clear_pct",
        label_override="Pivot Clear %",
        value_vs_rule=pivot_vr,
        rule_display=pivot_rule_disp,
    )

    base_len_min = _threshold_float("base_len_min_bars", 15.0)
    if base_len_min <= 0:
        base_len_min = 15.0
    base_val = _maybe_float(row.get("base_len_bars"))
    base_metric = _summarize_base_len(base_val, base_len_min)
    base_rule_value = f"{int(round(base_len_min))} bars"
    base_vr, base_rule_disp = _format_threshold_display(
        base_metric[1], base_rule_value, passed=base_metric[3], comparator="ge"
    )
    add(
        base_metric,
        code="base_len_bars",
        label_override="Base Length",
        value_vs_rule=base_vr,
        rule_display=base_rule_disp,
    )

    relvol_min = _threshold_float("breakout_relvol20_min", 1.5)
    relvol_val = _maybe_float(row.get("relvol20"))
    relvol_metric = _summarize_relvol(relvol_val, relvol_min, label="RelVol(20)")
    relvol_rule_value = _format_multiplier(relvol_min)
    relvol_vr, relvol_rule_disp = _format_threshold_display(
        relvol_metric[1], relvol_rule_value, passed=relvol_metric[3], comparator="ge"
    )
    add(
        relvol_metric,
        code="relvol20",
        label_override="RelVol(20)",
        value_vs_rule=relvol_vr,
        rule_display=relvol_rule_disp,
    )

    atr_lo, atr_hi = _threshold_range("atr10_pct_range", (3.0, 7.0))
    atr_source = row.get("atr10_pct")
    if atr_source is None:
        atr_source = row.get("atr_pct")
    atr_val = _maybe_float(atr_source)
    atr_metric = _summarize_atr(atr_val, atr_lo, atr_hi)
    atr_vr, atr_rule_disp = _format_range_display(
        atr_metric[1],
        atr_lo,
        atr_hi,
        _format_percent(atr_lo),
        _format_percent(atr_hi),
        passed=atr_metric[3],
        raw_value=atr_val,
    )
    add(
        atr_metric,
        code="atr10_pct",
        label_override="ATR10%",
        value_vs_rule=atr_vr,
        rule_display=atr_rule_disp,
    )

    adx_min = _threshold_float("adx14_min", 22.0)
    adx_source = row.get("adx")
    if adx_source is None:
        adx_source = row.get("adx14")
    adx_val = _maybe_float(adx_source)
    adx_metric = _summarize_adx(adx_val, adx_min)
    adx_rule_value = _format_int(adx_min)
    adx_vr, adx_rule_disp = _format_threshold_display(
        adx_metric[1], adx_rule_value, passed=adx_metric[3], comparator="ge"
    )
    add(
        adx_metric,
        code="adx14",
        label_override="ADX(14)",
        value_vs_rule=adx_vr,
        rule_display=adx_rule_disp,
    )

    prox_min = _threshold_float("proximity_52w_min_pct", -8.0)
    prox_source = row.get("pct_from_52w_high")
    if prox_source is None:
        prox_source = row.get("proximity_52w_high_pct")
    prox_val = _maybe_float(prox_source)
    prox_metric = _summarize_proximity(prox_val, prox_min)
    prox_rule_value = _format_percent(prox_min, include_sign=True)
    prox_vr, prox_rule_disp = _format_threshold_display(
        prox_metric[1], prox_rule_value, passed=prox_metric[3], comparator="ge"
    )
    add(
        prox_metric,
        code="pct_from_52w_high",
        label_override="52W Proximity",
        value_vs_rule=prox_vr,
        rule_display=prox_rule_disp,
    )

    day_cap = _threshold_float("day_change_cap_breakout_pct", 6.0)
    day_source = row.get("change_pct")
    if day_source is None:
        day_source = row.get("pct_today")
    day_val = _maybe_float(day_source)
    day_metric = _summarize_day_change(day_val, day_cap)
    day_rule_value = _format_percent(day_cap, include_sign=True)
    day_vr, day_rule_disp = _format_threshold_display(
        day_metric[1], day_rule_value, passed=day_metric[3], comparator="le"
    )
    add(
        day_metric,
        code="day_change_pct",
        label_override="Day % Change",
        value_vs_rule=day_vr,
        rule_display=day_rule_disp,
    )

    liquidity_floor = _threshold_float("liquidity_floor_rupees", 5e7)
    liquidity_source = row.get("liquidity")
    if liquidity_source is None:
        liquidity_source = row.get("median_traded_value_20d")
    liquidity_val = _maybe_float(liquidity_source)
    liquidity_metric = _summarize_liquidity(liquidity_val, liquidity_floor)
    liquidity_rule_value = _format_liquidity(liquidity_floor)
    liquidity_vr, liquidity_rule_disp = _format_threshold_display(
        liquidity_metric[1],
        liquidity_rule_value,
        passed=liquidity_metric[3],
        comparator="ge",
    )
    add(
        liquidity_metric,
        code="liquidity",
        label_override="Liquidity (Median 20D)",
        value_vs_rule=liquidity_vr,
        rule_display=liquidity_rule_disp,
    )

    return passed, reason_items, checklist_items


def _build_intraday_buy_metrics(row: Dict[str, Any]) -> Tuple[bool, List[ReasonItem], List[Dict[str, Any]]]:
    reason_items: List[ReasonItem] = []
    checklist_items: List[Dict[str, Any]] = []
    passed = True

    def add(
        metric: ReasonMetric,
        *,
        enforce: bool = True,
        code: str | None = None,
        label_override: str | None = None,
        value_vs_rule: str | None = None,
        rule_display: str | None = None,
    ) -> None:
        nonlocal passed
        label, value_str, desc, ok = metric
        factor_label = label_override or label.replace("_", " ").title()
        metric_code = code or label
        reason_items.append((factor_label, value_str, desc))
        checklist_items.append(
            {
                "code": metric_code,
                "factor": factor_label,
                "value_display": value_str,
                "value_vs_rule": value_vs_rule or value_str,
                "rule_display": rule_display,
                "description": desc,
                "passed": bool(ok),
                "enforced": bool(enforce),
            }
        )
        if enforce:
            passed = passed and bool(ok)

    score_min = _threshold_float("breakout_score_min", 70.0)
    base_score_metric = _summarize_score(row.get("score"), score_min)
    base_score_rule = _format_int(score_min)
    base_score_vr, base_score_rule_disp = _format_threshold_display(
        base_score_metric[1], base_score_rule, passed=base_score_metric[3], comparator="ge"
    )
    add(
        base_score_metric,
        enforce=False,
        code="score",
        label_override="Score",
        value_vs_rule=base_score_vr,
        rule_display=base_score_rule_disp,
    )

    pivot_lo, pivot_hi = _threshold_range("breakout_pivot_clear_pct_range", (1.0, 5.0))
    pivot_val = _maybe_float(row.get("pivot_clear_pct"))
    pivot_metric = _summarize_pivot(pivot_val, pivot_lo, pivot_hi)
    pivot_vr, pivot_rule_disp = _format_range_display(
        pivot_metric[1],
        pivot_lo,
        pivot_hi,
        _format_percent(pivot_lo, include_sign=True),
        _format_percent(pivot_hi, include_sign=True),
        passed=pivot_metric[3],
        raw_value=pivot_val,
    )
    add(
        pivot_metric,
        enforce=False,
        code="pivot_clear_pct",
        label_override="Pivot Clear %",
        value_vs_rule=pivot_vr,
        rule_display=pivot_rule_disp,
    )

    base_len_min = _threshold_float("base_len_min_bars", 15.0)
    if base_len_min <= 0:
        base_len_min = 15.0
    base_val = _maybe_float(row.get("base_len_bars"))
    base_metric = _summarize_base_len(base_val, base_len_min)
    base_rule_value = f"{int(round(base_len_min))} bars"
    base_vr, base_rule_disp = _format_threshold_display(
        base_metric[1], base_rule_value, passed=base_metric[3], comparator="ge"
    )
    add(
        base_metric,
        enforce=False,
        code="base_len_bars",
        label_override="Base Length",
        value_vs_rule=base_vr,
        rule_display=base_rule_disp,
    )

    starter_score_min = _threshold_float("starter_score_min_intraday", 65.0)
    intraday_score = row.get("intraday_score")
    if intraday_score is None:
        intraday_score = row.get("score")
    starter_metric = _summarize_score(intraday_score, starter_score_min, label="starter_score")
    starter_rule_value = _format_int(starter_score_min)
    starter_vr, starter_rule_disp = _format_threshold_display(
        starter_metric[1], starter_rule_value, passed=starter_metric[3], comparator="ge"
    )
    add(
        starter_metric,
        code="starter_score",
        label_override="Starter Score",
        value_vs_rule=starter_vr,
        rule_display=starter_rule_disp,
    )

    relvol_source = row.get("intraday_relvol")
    if relvol_source is None:
        relvol_source = row.get("relvol20") if row.get("relvol20") is not None else row.get("vol_spike")
    relvol_val = _maybe_float(relvol_source)
    relvol_min = _threshold_float("intraday_relvol_min", 1.5)
    relvol_metric = _summarize_relvol(relvol_val, relvol_min, label="RelVol")
    relvol_rule_value = _format_multiplier(relvol_min)
    relvol_vr, relvol_rule_disp = _format_threshold_display(
        relvol_metric[1], relvol_rule_value, passed=relvol_metric[3], comparator="ge"
    )
    add(
        relvol_metric,
        code="intraday_relvol",
        label_override="RelVol",
        value_vs_rule=relvol_vr,
        rule_display=relvol_rule_disp,
    )

    adx_min = _threshold_float("adx14_min", 22.0)
    adx_source = row.get("adx")
    if adx_source is None:
        adx_source = row.get("adx14")
    adx_val = _maybe_float(adx_source)
    adx_metric = _summarize_adx(adx_val, adx_min)
    adx_rule_value = _format_int(adx_min)
    adx_vr, adx_rule_disp = _format_threshold_display(
        adx_metric[1], adx_rule_value, passed=adx_metric[3], comparator="ge"
    )
    add(
        adx_metric,
        code="adx14",
        label_override="ADX(14)",
        value_vs_rule=adx_vr,
        rule_display=adx_rule_disp,
    )

    slope_metric = _summarize_adx_slope(row.get("adx_slope_pos"))
    slope_vr, slope_rule_disp = _format_boolean_display(
        slope_metric[1], "rising", passed=slope_metric[3]
    )
    add(
        slope_metric,
        code="adx_slope_pos",
        label_override="ADX Slope",
        value_vs_rule=slope_vr,
        rule_display=slope_rule_disp,
    )

    rsi_source = row.get("rsi")
    if rsi_source is None:
        rsi_source = row.get("rsi14")
    rsi_val = _maybe_float(rsi_source)
    rsi_metric = _summarize_rsi(rsi_val, 58.0, 70.0)
    rsi_vr, rsi_rule_disp = _format_range_display(
        rsi_metric[1],
        58.0,
        70.0,
        _format_int(58.0),
        _format_int(70.0),
        passed=rsi_metric[3],
        raw_value=rsi_val,
    )
    add(
        rsi_metric,
        code="rsi14",
        label_override="RSI(14)",
        value_vs_rule=rsi_vr,
        rule_display=rsi_rule_disp,
    )

    prox_min = _threshold_float("proximity_52w_min_pct", -8.0)
    prox_source = row.get("pct_from_52w_high")
    if prox_source is None:
        prox_source = row.get("proximity_52w_high_pct")
    prox_val = _maybe_float(prox_source)
    prox_metric = _summarize_proximity(prox_val, prox_min)
    prox_rule_value = _format_percent(prox_min, include_sign=True)
    prox_vr, prox_rule_disp = _format_threshold_display(
        prox_metric[1], prox_rule_value, passed=prox_metric[3], comparator="ge"
    )
    add(
        prox_metric,
        code="pct_from_52w_high",
        label_override="52W Proximity",
        value_vs_rule=prox_vr,
        rule_display=prox_rule_disp,
    )

    atr_lo, atr_hi = _threshold_range("atr10_pct_range", (3.0, 7.0))
    atr_source = row.get("atr10_pct")
    if atr_source is None:
        atr_source = row.get("atr_pct")
    atr_val = _maybe_float(atr_source)
    atr_metric = _summarize_atr(atr_val, atr_lo, atr_hi)
    atr_vr, atr_rule_disp = _format_range_display(
        atr_metric[1],
        atr_lo,
        atr_hi,
        _format_percent(atr_lo),
        _format_percent(atr_hi),
        passed=atr_metric[3],
        raw_value=atr_val,
    )
    add(
        atr_metric,
        code="atr10_pct",
        label_override="ATR10%",
        value_vs_rule=atr_vr,
        rule_display=atr_rule_disp,
    )

    day_cap = _threshold_float("day_change_cap_starter_pct", 4.0)
    day_source = row.get("change_pct")
    if day_source is None:
        day_source = row.get("pct_today")
    day_val = _maybe_float(day_source)
    day_metric = _summarize_day_change(day_val, day_cap)
    day_rule_value = _format_percent(day_cap, include_sign=True)
    day_vr, day_rule_disp = _format_threshold_display(
        day_metric[1], day_rule_value, passed=day_metric[3], comparator="le"
    )
    add(
        day_metric,
        code="day_change_pct",
        label_override="Day % Change",
        value_vs_rule=day_vr,
        rule_display=day_rule_disp,
    )

    liquidity_floor = _threshold_float("liquidity_floor_rupees", 5e7)
    liquidity_source = row.get("liquidity")
    if liquidity_source is None:
        liquidity_source = row.get("median_traded_value_20d")
    liquidity_val = _maybe_float(liquidity_source)
    liquidity_metric = _summarize_liquidity(liquidity_val, liquidity_floor)
    liquidity_rule_value = _format_liquidity(liquidity_floor)
    liquidity_vr, liquidity_rule_disp = _format_threshold_display(
        liquidity_metric[1],
        liquidity_rule_value,
        passed=liquidity_metric[3],
        comparator="ge",
    )
    add(
        liquidity_metric,
        code="liquidity",
        label_override="Liquidity (Median 20D)",
        value_vs_rule=liquidity_vr,
        rule_display=liquidity_rule_disp,
    )

    persistence_metric = _summarize_persistence(row.get("persistence_ok"))
    persistence_vr, persistence_rule_disp = _format_boolean_display(
        persistence_metric[1], "Yes", passed=persistence_metric[3]
    )
    add(
        persistence_metric,
        code="persistence_ok",
        label_override="Persistence",
        value_vs_rule=persistence_vr,
        rule_display=persistence_rule_disp,
    )

    return passed, reason_items, checklist_items


def _assemble_buy_checklist(
    mode: str,
    passed: bool,
    raw_items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    enforced_items = [item for item in raw_items if item.get("enforced", True)]
    total_items = len(enforced_items)
    passed_items = sum(1 for item in enforced_items if item.get("passed"))
    summary_prefix = "Yes" if passed else "No"
    summary = (
        summary_prefix
        if total_items == 0
        else f"{summary_prefix} — {passed_items} / {total_items} passed"
    )
    fail_parts = [
        f"{item['factor']} — {item['description']}"
        for item in raw_items
        if not item.get("passed") and item.get("description")
    ]
    public_items = [{k: v for k, v in item.items() if k != "enforced"} for item in raw_items]
    return {
        "label": f"BUY ({mode} gates)",
        "mode": mode,
        "passed": passed,
        "passed_items": passed_items,
        "total_items": total_items,
        "summary": summary,
        "fail_summary": "; ".join(fail_parts) if fail_parts else None,
        "items": public_items,
    }


def get_threshold_float(name: str, default: float) -> float:
    return _threshold_float(name, default)


def get_threshold_range(name: str, default: Tuple[float, float]) -> Tuple[float, float]:
    return _threshold_range(name, default)


def evaluate_buy_gate(row: Dict[str, Any]) -> Tuple[str, str, Dict[str, Any]]:
    is_eod = bool(row.get("is_eod"))
    mode = "EOD" if is_eod else "INTRADAY"
    row["buy_mode"] = mode
    passed, items, raw_checklist = (
        _build_eod_buy_metrics(row) if is_eod else _build_intraday_buy_metrics(row)
    )
    reason = compose_human_reason(items)
    checklist = _assemble_buy_checklist(mode, passed, raw_checklist)
    row["buy_checklist"] = checklist
    return ("Yes" if passed else "No"), reason, checklist
