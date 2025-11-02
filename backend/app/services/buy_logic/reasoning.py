from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from zoneinfo import ZoneInfo

from app.core import config as app_config

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from app.core.config import (
        StrategyBuyPersistenceConfig,
        StrategyBuyProfileConfig,
        StrategyConfig,
    )

__all__ = ["evaluate_buy_gate"]


LUNCH_WINDOW_DEFAULT: Tuple[time, time] = (time(12, 0), time(13, 15))


@dataclass
class CheckResult:
    code: str
    label: str
    rule: str
    actual: str
    passed: bool
    value: float | None = None

    def to_dict(self, *, include_value: bool = False) -> Dict[str, Any]:
        data = {
            "code": self.code,
            "label": self.label,
            "rule": self.rule,
            "actual": self.actual,
            "pass": self.passed,
        }
        if include_value:
            data["value"] = self.value
        return data


CHECK_LABELS: Dict[str, str] = {
    "min_score": "Score",
    "pivot_clear_pct": "Pivot Clear %",
    "base_len_min_bars": "Base Length",
    "prox52w_min_pct": "52W Proximity %",
    "relvol20_min": "RelVol20",
    "intraday_relvol_min": "Intraday RelVol",
    "adx14_min": "ADX14",
    "atr_pct": "ATR% (10d)",
    "day_change_max_pct": "Day % Change",
    "liquidity_min_traded_value_20d": "Liquidity (Median 20D)",
    "starter_score_min_intraday": "Starter Score",
    "persistence": "Persistence",
}

EOD_CHECK_ORDER: List[str] = [
    "min_score",
    "pivot_clear_pct",
    "base_len_min_bars",
    "prox52w_min_pct",
    "relvol20_min",
    "adx14_min",
    "atr_pct",
    "day_change_max_pct",
    "liquidity_min_traded_value_20d",
]

INTRADAY_CHECK_ORDER: List[str] = [
    "starter_score_min_intraday",
    "intraday_relvol_min",
    "adx14_min",
    "prox52w_min_pct",
    "atr_pct",
    "day_change_max_pct",
    "liquidity_min_traded_value_20d",
    "persistence",
]


@lru_cache(maxsize=1)
def _strategy() -> "StrategyConfig":
    return app_config.get_settings().strategy


@lru_cache(maxsize=1)
def _trading_window() -> Tuple[ZoneInfo, time, time]:
    settings = app_config.get_settings()
    tw = getattr(settings.scheduler, "trading_window", None)
    tz_name = getattr(tw, "tz", None) or "Asia/Kolkata"
    tz = ZoneInfo(tz_name)
    start_str = getattr(tw, "start", None) or "09:15"
    end_str = getattr(tw, "end", None) or "15:30"
    return tz, _parse_time(start_str, default=time(9, 15)), _parse_time(end_str, default=time(15, 30))


def _parse_time(value: Any, *, default: time) -> time:
    if isinstance(value, time):
        return value
    if isinstance(value, str):
        parts = value.strip().split(":")
        try:
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
            second = int(parts[2]) if len(parts) > 2 else 0
            return time(hour % 24, minute % 60, second % 60)
        except Exception:
            return default
    return default


def _coerce_float(value: Any) -> float | None:
    if value in (None, "", "None"):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def _coerce_int(value: Any) -> Optional[int]:
    val = _coerce_float(value)
    if val is None:
        return None
    try:
        return int(round(val))
    except Exception:
        return None


def _boolish(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        s = value.strip().lower()
        if not s:
            return None
        if s in {"1", "true", "yes", "y", "on"}:
            return True
        if s in {"0", "false", "no", "n", "off"}:
            return False
    return None


def _format_number(value: Optional[float], *, decimals: int = 0) -> str:
    if value is None:
        return "NA"
    return f"{value:.{decimals}f}"


def _format_percent(value: Optional[float], *, decimals: int = 1, include_sign: bool = True) -> str:
    if value is None:
        return "NA"
    if include_sign:
        return f"{value:+.{decimals}f}%"
    return f"{value:.{decimals}f}%"


def _format_multiplier(value: Optional[float], *, decimals: int = 1) -> str:
    if value is None:
        return "NA"
    return f"{value:.{decimals}f}x"


def _format_currency_cr(value: Optional[float]) -> str:
    if value is None:
        return "NA"
    cr = value / 1e7
    return f"₹{cr:.1f} Cr"


def _format_range(lo: Optional[float], hi: Optional[float], *, unit: str) -> str:
    if unit == "percent":
        conv = lambda v: _format_percent(v, decimals=1, include_sign=True)
    elif unit == "multiplier":
        conv = lambda v: _format_multiplier(v, decimals=1)
    else:
        conv = lambda v: _format_number(v, decimals=1)

    if lo is not None and hi is not None:
        return f"in [{conv(lo)}, {conv(hi)}]"
    if lo is not None:
        return f">= {conv(lo)}"
    if hi is not None:
        return f"<= {conv(hi)}"
    return "configured"


def _resolve_eval_dt(row: Dict[str, Any], eval_time: Optional[datetime]) -> datetime:
    candidates: List[datetime] = []
    raw_as_of = row.get("as_of")
    if isinstance(raw_as_of, datetime):
        dt = raw_as_of if raw_as_of.tzinfo else raw_as_of.replace(tzinfo=timezone.utc)
        candidates.append(dt)
    elif isinstance(raw_as_of, str) and raw_as_of.strip():
        text = raw_as_of.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
            dt = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            candidates.append(dt)
        except Exception:
            pass
    if eval_time:
        candidates.append(eval_time if eval_time.tzinfo else eval_time.replace(tzinfo=timezone.utc))
    if not candidates:
        candidates.append(datetime.now(timezone.utc))
    return candidates[0].astimezone(timezone.utc)


def _minutes_since_open(eval_dt: datetime) -> int:
    tz, start, _ = _trading_window()
    local_dt = eval_dt.astimezone(tz)
    minutes = (local_dt.hour * 60 + local_dt.minute) - (start.hour * 60 + start.minute)
    return max(minutes, 0)


def _in_lunch_window(eval_dt: datetime, window: Tuple[time, time]) -> bool:
    tz, _, _ = _trading_window()
    local_dt = eval_dt.astimezone(tz)
    start, end = window
    t = local_dt.time()
    if start <= end:
        return start <= t < end
    return t >= start or t < end


def _resolve_profile(is_eod: bool) -> Tuple[str, Optional["StrategyBuyProfileConfig"]]:
    profiles = _strategy().profiles.buy or {}
    code = "swing_eod" if is_eod else "intraday_breakout"
    profile = profiles.get(code)
    return code, profile


def _build_min_score(row: Dict[str, Any], profile: "StrategyBuyProfileConfig", **_: Any) -> CheckResult:
    threshold = _coerce_float(getattr(profile, "min_score", None))
    value = _coerce_float(row.get("score"))
    passed = value is not None and threshold is not None and value >= threshold
    rule = f">= {_format_number(threshold, decimals=0)}" if threshold is not None else ">= N/A"
    actual = _format_number(value, decimals=0)
    return CheckResult("min_score", CHECK_LABELS["min_score"], rule, actual, passed, value=value)


def _build_starter_score(row: Dict[str, Any], profile: "StrategyBuyProfileConfig", **_: Any) -> CheckResult:
    threshold = _coerce_float(getattr(profile, "starter_score_min_intraday", None))
    value = _coerce_float(row.get("starter_score") or row.get("score"))
    passed = value is not None and threshold is not None and value >= threshold
    rule = f">= {_format_number(threshold, decimals=0)}" if threshold is not None else ">= N/A"
    actual = _format_number(value, decimals=0)
    return CheckResult(
        "starter_score_min_intraday",
        CHECK_LABELS["starter_score_min_intraday"],
        rule,
        actual,
        passed,
        value=value,
    )


def _build_pivot_clear(row: Dict[str, Any], profile: "StrategyBuyProfileConfig", **_: Any) -> CheckResult:
    rng = getattr(profile, "pivot_clear_pct", None)
    lo = _coerce_float(getattr(rng, "min", None)) if rng else None
    hi = _coerce_float(getattr(rng, "max", None)) if rng else None
    value = _coerce_float(row.get("pivot_clear_pct"))
    passed = True
    if lo is not None and (value is None or value < lo):
        passed = False
    if hi is not None and (value is None or value > hi):
        passed = False
    rule = _format_range(lo, hi, unit="percent")
    actual = _format_percent(value, decimals=1, include_sign=True)
    return CheckResult("pivot_clear_pct", CHECK_LABELS["pivot_clear_pct"], rule, actual, passed, value=value)


def _build_base_length(row: Dict[str, Any], profile: "StrategyBuyProfileConfig", **_: Any) -> CheckResult:
    threshold = _coerce_int(getattr(profile, "base_len_min_bars", None))
    value = _coerce_int(row.get("base_len_bars"))
    passed = value is not None and threshold is not None and value >= threshold
    rule = f">= {threshold} bars" if threshold is not None else ">= N/A"
    actual = f"{value} bars" if value is not None else "NA"
    return CheckResult("base_len_min_bars", CHECK_LABELS["base_len_min_bars"], rule, actual, passed, value=float(value) if value is not None else None)


def _build_proximity(row: Dict[str, Any], profile: "StrategyBuyProfileConfig", **_: Any) -> CheckResult:
    threshold = _coerce_float(getattr(profile, "prox52w_min_pct", None))
    value = _coerce_float(row.get("proximity_52w_high_pct") or row.get("pct_from_52w_high"))
    passed = value is not None and threshold is not None and value >= threshold
    rule = f">= {_format_percent(threshold, decimals=1, include_sign=True)}" if threshold is not None else ">= N/A"
    actual = _format_percent(value, decimals=1, include_sign=True)
    return CheckResult("prox52w_min_pct", CHECK_LABELS["prox52w_min_pct"], rule, actual, passed, value=value)


def _build_relvol20(row: Dict[str, Any], profile: "StrategyBuyProfileConfig", **_: Any) -> CheckResult:
    threshold = _coerce_float(getattr(profile, "relvol20_min", None))
    value = _coerce_float(row.get("relvol20"))
    passed = value is not None and threshold is not None and value >= threshold
    rule = f">= {_format_multiplier(threshold, decimals=1)}" if threshold is not None else ">= N/A"
    actual = _format_multiplier(value, decimals=1)
    return CheckResult("relvol20_min", CHECK_LABELS["relvol20_min"], rule, actual, passed, value=value)


def _build_intraday_relvol(row: Dict[str, Any], profile: "StrategyBuyProfileConfig", **_: Any) -> CheckResult:
    threshold = _coerce_float(getattr(profile, "intraday_relvol_min", None))
    value = _coerce_float(row.get("intraday_relvol") or row.get("relvol20"))
    passed = value is not None and threshold is not None and value >= threshold
    rule = f">= {_format_multiplier(threshold, decimals=1)}" if threshold is not None else ">= N/A"
    actual = _format_multiplier(value, decimals=1)
    return CheckResult("intraday_relvol_min", CHECK_LABELS["intraday_relvol_min"], rule, actual, passed, value=value)


def _build_adx14(row: Dict[str, Any], profile: "StrategyBuyProfileConfig", **_: Any) -> CheckResult:
    threshold = _coerce_float(getattr(profile, "adx14_min", None))
    value = _coerce_float(row.get("adx14") or row.get("adx"))
    passed = value is not None and threshold is not None and value >= threshold
    rule = f">= {_format_number(threshold, decimals=0)}" if threshold is not None else ">= N/A"
    actual = _format_number(value, decimals=0)
    return CheckResult("adx14_min", CHECK_LABELS["adx14_min"], rule, actual, passed, value=value)


def _build_atr_pct(row: Dict[str, Any], profile: "StrategyBuyProfileConfig", **_: Any) -> CheckResult:
    rng = getattr(profile, "atr_pct", None)
    lo = _coerce_float(getattr(rng, "min", None)) if rng else None
    hi = _coerce_float(getattr(rng, "max", None)) if rng else None
    value = _coerce_float(row.get("atr10_pct") or row.get("atr_pct") or row.get("atr14_pct"))
    passed = True
    if lo is not None and (value is None or value < lo):
        passed = False
    if hi is not None and (value is None or value > hi):
        passed = False
    rule = _format_range(lo, hi, unit="percent")
    actual = _format_percent(value, decimals=1, include_sign=False)
    return CheckResult("atr_pct", CHECK_LABELS["atr_pct"], rule, actual, passed, value=value)


def _build_day_change(row: Dict[str, Any], profile: "StrategyBuyProfileConfig", **_: Any) -> CheckResult:
    cap = _coerce_float(getattr(profile, "day_change_max_pct", None))
    value = _coerce_float(row.get("change_pct") or row.get("pct_today"))
    passed = value is not None and cap is not None and value <= cap
    rule = f"<= {_format_percent(cap, decimals=1, include_sign=True)}" if cap is not None else "<= N/A"
    actual = _format_percent(value, decimals=1, include_sign=True)
    return CheckResult("day_change_max_pct", CHECK_LABELS["day_change_max_pct"], rule, actual, passed, value=value)


def _build_liquidity(row: Dict[str, Any], profile: "StrategyBuyProfileConfig", **_: Any) -> CheckResult:
    threshold = _coerce_float(getattr(profile, "liquidity_min_traded_value_20d", None))
    value = _coerce_float(row.get("liquidity") or row.get("median_traded_value_20d"))
    passed = value is not None and threshold is not None and value >= threshold
    rule = f">= {_format_currency_cr(threshold)}" if threshold is not None else ">= N/A"
    actual = _format_currency_cr(value)
    return CheckResult(
        "liquidity_min_traded_value_20d",
        CHECK_LABELS["liquidity_min_traded_value_20d"],
        rule,
        actual,
        passed,
        value=value,
    )


def _build_persistence(
    row: Dict[str, Any],
    profile: "StrategyBuyProfileConfig",
    *,
    eval_dt: datetime,
) -> Tuple[CheckResult, Dict[str, Any]]:
    persistence_cfg = getattr(profile, "persistence", None)
    if not isinstance(persistence_cfg, object):
        return (
            CheckResult("persistence", CHECK_LABELS["persistence"], "configured", "NA", False, value=None),
            {},
        )

    require_above_vwap = bool(getattr(persistence_cfg, "require_above_vwap", False))
    require_pdh_clear = bool(getattr(persistence_cfg, "require_prev_day_high_clear", False))
    min_minutes = int(getattr(persistence_cfg, "min_minutes_since_open", 0) or 0)
    avoid_lunch = bool(getattr(persistence_cfg, "avoid_lunch_window", False))

    above_vwap = _boolish(row.get("above_vwap"))
    if above_vwap is None:
        price = _coerce_float(row.get("last"))
        vwap = _coerce_float(row.get("intraday_vwap") or row.get("vwap"))
        if price is not None and vwap is not None:
            above_vwap = price >= vwap

    prev_day_high_clear = _boolish(row.get("prev_day_high_clear"))
    if prev_day_high_clear is None:
        prev_high = _coerce_float(row.get("prev_day_high") or row.get("pdh"))
        price = _coerce_float(row.get("last"))
        if prev_high is not None and price is not None:
            prev_day_high_clear = price >= prev_high

    minutes_since_open = _coerce_int(row.get("minutes_since_open"))
    if minutes_since_open is None:
        minutes_since_open = _minutes_since_open(eval_dt)

    lunch_flag = _boolish(row.get("in_lunch_window"))
    if lunch_flag is None:
        lunch_flag = _in_lunch_window(eval_dt, LUNCH_WINDOW_DEFAULT)

    passed = True
    if require_above_vwap and not (above_vwap is True):
        passed = False
    if require_pdh_clear and not (prev_day_high_clear is True):
        passed = False
    if min_minutes > 0 and (minutes_since_open is None or minutes_since_open < min_minutes):
        passed = False
    if avoid_lunch and lunch_flag:
        passed = False

    requirements: List[str] = []
    if require_above_vwap:
        requirements.append("above VWAP")
    if require_pdh_clear:
        requirements.append("PDH cleared")
    if min_minutes > 0:
        requirements.append(f">= {min_minutes}m from open")
    if avoid_lunch:
        requirements.append("outside lunch")
    rule = ", ".join(requirements) if requirements else "configured"

    actual_fragments = [
        "VWAP ok" if above_vwap else "VWAP fail",
        "PDH ok" if prev_day_high_clear else "PDH fail",
        f"{minutes_since_open}m" if minutes_since_open is not None else "mins n/a",
    ]
    if avoid_lunch:
        actual_fragments.append("lunch" if lunch_flag else "not lunch")
    actual = "; ".join(actual_fragments)

    detail = {
        "above_vwap": above_vwap,
        "prev_day_high_clear": prev_day_high_clear,
        "minutes_since_open": minutes_since_open,
        "lunch_window_hit": lunch_flag if avoid_lunch else None,
    }

    return (
        CheckResult("persistence", CHECK_LABELS["persistence"], rule, actual, passed, value=None),
        detail,
    )


def _evaluate_checks(
    row: Dict[str, Any],
    profile: "StrategyBuyProfileConfig",
    codes: List[str],
    *,
    eval_dt: datetime,
) -> Tuple[Dict[str, CheckResult], Dict[str, Any]]:
    checks: Dict[str, CheckResult] = {}
    meta: Dict[str, Any] = {}
    for code in codes:
        builder = _CHECK_BUILDERS.get(code)
        if builder is None:
            continue
        result = builder(row, profile, eval_dt=eval_dt)
        if isinstance(result, tuple):
            check, extra = result
        else:
            check, extra = result, None
        checks[code] = check
        if extra:
            meta[code] = extra
    return checks, meta


def _compose_reasons(checks: Dict[str, CheckResult], mode: str) -> Tuple[str, List[str]]:
    parts: List[str] = []

    score_chk = checks.get("min_score")
    if score_chk and score_chk.passed and score_chk.value is not None:
        parts.append(f"Score {int(round(score_chk.value))}")

    starter_chk = checks.get("starter_score_min_intraday")
    if starter_chk and starter_chk.passed and starter_chk.value is not None:
        parts.append(f"Starter {int(round(starter_chk.value))}")

    relvol_chk = checks.get("relvol20_min")
    if relvol_chk and relvol_chk.passed and relvol_chk.value is not None:
        parts.append(f"RelVol20 {relvol_chk.value:.1f}x")

    intrarelvol_chk = checks.get("intraday_relvol_min")
    if intrarelvol_chk and intrarelvol_chk.passed and intrarelvol_chk.value is not None:
        parts.append(f"IntrRelVol {intrarelvol_chk.value:.1f}x")

    adx_chk = checks.get("adx14_min")
    if adx_chk and adx_chk.passed and adx_chk.value is not None:
        parts.append(f"ADX14 {int(round(adx_chk.value))}")

    atr_chk = checks.get("atr_pct")
    if atr_chk and atr_chk.passed and atr_chk.value is not None:
        parts.append(f"ATR% {atr_chk.value:.1f}")

    prox_chk = checks.get("prox52w_min_pct")
    if prox_chk and prox_chk.passed and prox_chk.value is not None:
        if prox_chk.value >= -2.0:
            parts.append("near 52W")
        else:
            parts.append(f"52W {prox_chk.value:+.1f}%")

    liquidity_chk = checks.get("liquidity_min_traded_value_20d")
    if liquidity_chk and liquidity_chk.passed:
        parts.append("Liquid")

    persistence_chk = checks.get("persistence")
    if mode == "INTRADAY" and persistence_chk and persistence_chk.passed:
        parts.append("Persistence ok")

    day_change_chk = checks.get("day_change_max_pct")
    if day_change_chk and day_change_chk.passed and day_change_chk.value is not None:
        parts.append(f"Day {day_change_chk.value:+.1f}%")

    ordered = parts[:6]
    return "; ".join(ordered), ordered


def evaluate_buy_gate(row: Dict[str, Any], *, eval_time: Optional[datetime] = None) -> Dict[str, Any]:
    eval_dt = _resolve_eval_dt(row, eval_time)
    is_eod = bool(row.get("is_eod"))
    mode = "EOD" if is_eod else "INTRADAY"
    profile_code, profile = _resolve_profile(is_eod)

    if profile is None:
        return {
            "profile": profile_code,
            "mode": mode,
            "flag": False,
            "pass_count": 0,
            "total_count": 0,
            "buy_checks": [],
            "checks": {},
            "failed_codes": [],
            "buy_failed_codes": [],
            "reasons_inline": "",
            "reason_parts": [],
            "eval_ts": eval_dt.isoformat(),
            "enforced_checks": [],
        }

    codes = EOD_CHECK_ORDER if is_eod else INTRADAY_CHECK_ORDER
    checks_map, meta = _evaluate_checks(row, profile, codes, eval_dt=eval_dt)

    enforced = list(getattr(profile, "enforced_checks", []) or [])
    if not enforced:
        enforced = EOD_CHECK_ORDER[:] if is_eod else INTRADAY_CHECK_ORDER[:]
    else:
        order = EOD_CHECK_ORDER if is_eod else INTRADAY_CHECK_ORDER
        enforced = [code for code in order if code in enforced]
    buy_checks: List[Dict[str, Any]] = []
    pass_count = 0
    failed_codes: List[str] = []

    for code in enforced:
        check = checks_map.get(code)
        if check is None:
            label = CHECK_LABELS.get(code, code)
            check = CheckResult(code=code, label=label, rule="not configured", actual="NA", passed=False, value=None)
            checks_map[code] = check
        if check.passed:
            pass_count += 1
        else:
            failed_codes.append(code)
        buy_checks.append(check.to_dict())

    total_count = len(enforced)
    flag = total_count > 0 and pass_count == total_count

    reasons_inline, reason_parts = _compose_reasons(checks_map, mode)

    evaluation: Dict[str, Any] = {
        "profile": profile_code,
        "mode": mode,
        "flag": flag,
        "pass_count": pass_count,
        "total_count": total_count,
        "buy_checks": buy_checks,
        "checks": {code: chk.to_dict(include_value=True) for code, chk in checks_map.items()},
        "failed_codes": failed_codes,
        "buy_failed_codes": failed_codes,
        "reasons_inline": reasons_inline,
        "reason_parts": reason_parts,
        "human_reason": reasons_inline,
        "eval_ts": eval_dt.isoformat(),
        "enforced_checks": enforced,
    }
    if meta:
        evaluation["debug"] = meta
    return evaluation


_CHECK_BUILDERS: Dict[str, Any] = {
    "min_score": _build_min_score,
    "pivot_clear_pct": _build_pivot_clear,
    "base_len_min_bars": _build_base_length,
    "prox52w_min_pct": _build_proximity,
    "relvol20_min": _build_relvol20,
    "intraday_relvol_min": _build_intraday_relvol,
    "adx14_min": _build_adx14,
    "atr_pct": _build_atr_pct,
    "day_change_max_pct": _build_day_change,
    "liquidity_min_traded_value_20d": _build_liquidity,
    "starter_score_min_intraday": _build_starter_score,
    "persistence": _build_persistence,
}
