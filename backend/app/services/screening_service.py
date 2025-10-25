# backend/app/services/screening_service.py
from __future__ import annotations
from datetime import datetime, timezone, time as dtime, timedelta
from functools import lru_cache
from typing import Optional, Tuple, Dict, Any, List
import logging
from uuid import uuid4

import pyarrow as pa
import pandas as pd
import numpy as np
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy.orm import Session
from zoneinfo import ZoneInfo

from app.repos.sql.jobs_repo import SqlJobsRepo
from app.repos.sql.history_repo import SqlHistoryRepo
from app.repos.parquet import datasets

# Contract-first models (generated)
from app.schemas.runs import RunDetail, Counts

from app.core import config as app_config
from app.repos.parquet.universe_repo import UniverseRepo
from app.adapters.yahoo_adapter import YahooAdapter  # ctor takes NO args

import yfinance as yf

# Phase 11 domain helpers (vectorized)
from app.domain.indicators import compute_indicator_frame
from app.domain.scoring import compute_score
from app.domain.rules.next_action import global_pre_gates, compute_next_action

log = logging.getLogger(__name__)

_ALLOWED_PRESETS = {"NIFTY50", "NIFTY100", "NIFTY500", "MIDCAP", "SMALLCAP", "ALL"}
_FALLBACK_NSE = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS"]


# --------------------------- time helpers ---------------------------

def _utcnow_aware() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)

def _to_aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

def _as_of_date_str(as_of_val: Optional[str]) -> Optional[str]:
    """
    Return YYYY-MM-DD if payload.as_of is present (date or ISO datetime),
    else None. Tolerant to '2025-09-21', '2025-09-21T10:00:00Z', etc.
    """
    if not as_of_val:
        return None
    s = str(as_of_val).strip()
    # if it's already a date string
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    try:
        return pd.to_datetime(s).strftime("%Y-%m-%d")
    except Exception:
        return None


def _parse_time_str(value: Optional[str], fallback: dtime) -> dtime:
    """
    Parse HH:MM (optionally with seconds) strings into time objects.
    Returns fallback when parsing fails.
    """
    if not value:
        return fallback
    try:
        parts = str(value).strip().split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        second = int(parts[2]) if len(parts) > 2 else 0
        hour = max(0, min(23, hour))
        minute = max(0, min(59, minute))
        second = max(0, min(59, second))
        return dtime(hour=hour, minute=minute, second=second)
    except Exception:
        return fallback


def _resolve_trading_window(cfg: Any) -> Dict[str, str]:
    """
    Extract scheduler.trading_window fields with reasonable defaults.
    """
    defaults = {"tz": "Asia/Kolkata", "start": "09:15", "end": "15:30"}
    scheduler_cfg = getattr(cfg, "scheduler", None)
    tw = getattr(scheduler_cfg, "trading_window", None)
    if hasattr(tw, "model_dump"):
        tw = tw.model_dump()
    elif hasattr(tw, "dict"):
        tw = tw.dict()
    if not isinstance(tw, dict):
        return defaults
    resolved = defaults.copy()
    for key in ("tz", "start", "end"):
        value = tw.get(key)
        if isinstance(value, str) and value.strip():
            resolved[key] = value.strip()
    return resolved


def _should_mark_eod_snapshot(
    *,
    now_utc: datetime,
    as_of_date: Optional[str],
    intraday_trading_date: Optional[str],
    cfg: Any,
) -> bool:
    """
    Decide whether the current screening run should be marked as EOD.
    - Explicit as_of (manual/backfill) always yields EOD.
    - Otherwise, when the run executes outside trading hours (after market close)
      for the targeted trading date, treat it as EOD.
    """
    if as_of_date:
        return True

    try:
        window = _resolve_trading_window(cfg or {})
        tz = ZoneInfo(str(window.get("tz") or "Asia/Kolkata"))
    except Exception:
        return False

    now_local = now_utc.astimezone(tz)
    target_day_str = intraday_trading_date or now_local.date().isoformat()
    try:
        target_day = datetime.strptime(target_day_str, "%Y-%m-%d").date()
    except Exception:
        target_day = now_local.date()

    start_time = _parse_time_str(window.get("start"), dtime(hour=9, minute=15))
    end_time = _parse_time_str(window.get("end"), dtime(hour=15, minute=30))

    start_dt = datetime.combine(target_day, start_time, tzinfo=tz)
    end_dt = datetime.combine(target_day, end_time, tzinfo=tz)

    if end_time <= start_time:
        # Overnight window (rare but supported) -> treat end on next day.
        end_dt = end_dt + timedelta(days=1)
        if now_local < start_dt:
            # Before overnight window start => already past previous close
            return now_local.date() > target_day

    if now_local >= end_dt:
        return True
    if now_local.date() > target_day:
        return True

    return False


# --------------------------- IO helpers -----------------------------

def _ensure_parquet_root() -> None:
    root = datasets.get_parquet_root()
    root.mkdir(parents=True, exist_ok=True)
    # truthy, once per process (datasets.py also logs root; duplicating here is intentional for service logs)
    try:
        log.info("parquet_root_resolved(service)", extra={"root": str(root.resolve())})
    except Exception:
        pass


def _find_committed_run_for_as_of(as_of_date: str) -> Optional[str]:
    # Return the run_id of a committed daily snapshot for the given as_of, if any.
    try:
        as_of_root = datasets.scores_daily_dir(as_of_date)
        cands = []
        for child in as_of_root.glob("run_id=*"):
            if child.is_dir() and (child / "_SUCCESS").exists():
                rid = child.name.split("run_id=", 1)[-1]
                cands.append(rid)
        return sorted(cands)[-1] if cands else None
    except Exception:
        return None

def _history_df(symbol: str, period: str = "400d") -> pd.DataFrame:
    """
    Pull ~18 months of daily candles (adj close, ohlc, volume) for indicators.
    We use yfinance directly here to keep adapter changes minimal.
    """
    try:
        t = yf.Ticker(symbol)
        df = t.history(period=period, interval="1d", auto_adjust=False)
    except Exception:
        df = None
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.rename(columns=str.lower)
    # normalize core columns
    for need in ["open", "high", "low", "close", "volume"]:
        if need not in df.columns:
            df[need] = np.nan
    # adj close if present; else fallback to close
    if "adj close" in df.columns:
        df["adj_close"] = df["adj close"].astype(float)
    else:
        df["adj_close"] = df["close"].astype(float)
    return df


# ---------------------- indicators computation ----------------------

def _compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute all indicators used by the Screener at the row's as_of.
    """
    return compute_indicator_frame(df)


def _resolve_nifty_regime(as_of_date: Optional[str]) -> Optional[str]:
    df = _history_df("^NSEI", period="400d")
    if df.empty:
        return None
    if as_of_date:
        try:
            cutoff = pd.to_datetime(as_of_date).date()
            mask = pd.Series(df.index.date <= cutoff, index=df.index)
            df = df.loc[mask[mask].index]
        except Exception:
            pass
    if df.empty:
        return None
    ind = _compute_indicators(df)
    if ind.empty:
        return None
    close_val = _maybe_float(df["close"].iloc[-1])
    ema50 = _maybe_float(ind["ema50"].iloc[-1])
    ema200 = _maybe_float(ind["ema200"].iloc[-1])
    if close_val is None or ema50 is None or ema200 is None:
        return None
    if close_val > ema200 and ema50 > ema200:
        return "UP"
    if close_val < ema200:
        return "DOWN"
    return "NEUTRAL"


def _count_upper_circuit_hits(df: pd.DataFrame, lookback: int = 60, threshold_pct: float = 9.9) -> int:
    if df is None or df.empty or "close" not in df.columns:
        return 0
    try:
        closes = df["close"].astype(float)
    except Exception:
        return 0
    pct_change = closes.pct_change() * 100.0
    window = pct_change.dropna().tail(lookback)
    if window.empty:
        return 0
    return int((window >= threshold_pct).sum())


# ---------------------- row construction ---------------------------

def _maybe_float(v):
    try:
        if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
            return None
        return float(v)
    except Exception:
        return None


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


BUY_ACTION_CODES = {"BUY_BREAKOUT", "BUY_PULLBACK", "BUY_STARTER"}


def _resolve_persistence_config() -> Dict[str, Any]:
    bars = 3
    score_min = _threshold_float("starter_score_min_intraday", 65.0)
    relvol_min = _threshold_float("intraday_relvol_min", 1.5)
    prox_min = _threshold_float("proximity_52w_min_pct", -8.0)
    return {
        "bars": max(int(bars), 1),
        "score_min": score_min,
        "relvol_min": relvol_min,
        "proximity_min": prox_min,
        "require_buy_flag": False,
        "require_action": True,
        "require_pre_gates": True,
        "require_above_pivot": True,
    }


def _normalize_persistence_snapshot(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    symbol = row.get("symbol")
    if not symbol:
        return None
    relvol_val = row.get("intraday_relvol")
    if relvol_val is None:
        relvol_val = row.get("relvol20")
    next_action = row.get("next_action") or row.get("next_action_code")
    pre_raw = row.get("pre_gates_pass")
    if isinstance(pre_raw, bool):
        pre_bool = pre_raw
    else:
        pre_bool = str(pre_raw or "").strip().lower() in {"1", "true", "yes", "y"}
    return {
        "score": _maybe_float(row.get("score")),
        "relvol": _maybe_float(relvol_val),
        "proximity": _maybe_float(row.get("proximity_52w_high_pct") or row.get("pct_from_52w_high")),
        "buy_flag": str(row.get("buy") or "").strip().upper(),
        "next_action": str(next_action or "").strip().upper(),
        "pre_gates_pass": pre_bool,
        "pivot": _maybe_float(row.get("pivot_high_20")),
        "last": _maybe_float(row.get("last")),
    }


def _compute_persistence_ok(
    current_snapshot: Dict[str, Any],
    history_snapshots: List[Dict[str, Any]],
    cfg: Dict[str, Any],
) -> bool:
    bars_required = max(int(cfg.get("bars", 3)), 1)
    if bars_required <= 1:
        return True
    window = list(history_snapshots[-(bars_required - 1) :])
    window.append(current_snapshot)
    if len(window) < bars_required:
        return False

    score_min = float(cfg.get("score_min", 0.0))
    relvol_min = float(cfg.get("relvol_min", 0.0))
    prox_min = float(cfg.get("proximity_min", -100.0))
    require_buy_flag = bool(cfg.get("require_buy_flag", False))
    require_action = bool(cfg.get("require_action", False))
    require_pre_gates = bool(cfg.get("require_pre_gates", False))
    require_above_pivot = bool(cfg.get("require_above_pivot", False))

    for snap in window:
        score = snap.get("score")
        relvol = snap.get("relvol")
        proximity = snap.get("proximity")
        buy_flag = snap.get("buy_flag", "")
        next_action = snap.get("next_action", "")
        pre_gates = bool(snap.get("pre_gates_pass"))
        pivot = snap.get("pivot")
        last_price = snap.get("last")

        if score is None or score < score_min:
            return False
        if relvol is None or relvol < relvol_min:
            return False
        if proximity is None or proximity < prox_min:
            return False
        if require_buy_flag and buy_flag != "YES":
            return False
        if require_action and next_action not in BUY_ACTION_CODES:
            return False
        if require_pre_gates and not pre_gates:
            return False
        if require_above_pivot and pivot is not None and last_price is not None and last_price < pivot:
            return False
    return True


def _load_persistence_history(
    date_str: Optional[str],
    current_run_id: Optional[str],
    bars_required: int,
) -> Dict[str, List[Dict[str, Any]]]:
    if not date_str or not current_run_id or bars_required <= 1:
        return {}
    try:
        runs = datasets.list_intraday_runs(date_str)
    except Exception:
        runs = []
    if not runs:
        return {}
    prior_runs = [rid for rid in runs if rid < str(current_run_id)]
    if not prior_runs:
        return {}
    needed = prior_runs[-(bars_required - 1) :]
    if not needed:
        return {}
    columns = [
        "symbol",
        "score",
        "relvol20",
        "intraday_relvol",
        "proximity_52w_high_pct",
        "pct_from_52w_high",
        "buy",
        "next_action",
        "next_action_code",
        "pre_gates_pass",
        "pivot_high_20",
        "last",
    ]
    history: Dict[str, List[Dict[str, Any]]] = {}
    for rid in needed:
        try:
            table = datasets.scan_scores_intraday(date_str, rid, columns=columns)
            records = table.to_pylist()
        except Exception:
            records = []
        for rec in records:
            sym = rec.get("symbol")
            if not sym:
                continue
            snapshot = _normalize_persistence_snapshot(rec)
            if snapshot is None:
                continue
            history.setdefault(str(sym), []).append(snapshot)
    return history


def _format_percent(value: Optional[float], decimals: int = 1, include_sign: bool = False) -> str:
    if value is None:
        return "NA"
    if include_sign:
        return f"{value:+.{decimals}f}%"
    return f"{value:.{decimals}f}%"


def _format_multiplier(value: Optional[float], decimals: int = 1) -> str:
    if value is None:
        return "NA"
    return f"{value:.{decimals}f}x"


def _format_int(value: Optional[float]) -> str:
    if value is None:
        return "NA"
    return str(int(round(value)))


def _format_liquidity(value: Optional[float]) -> str:
    if value is None:
        return "NA"
    # Convert to crore units to keep numbers readable
    return f"{value / 1e7:.1f}Cr"


def _summarize_score(value: Any, minimum: float, label: str = "Score") -> Tuple[str, str, str, bool]:
    val = _maybe_float(value)
    if val is None:
        return label, "NA", "score unavailable", False
    value_str = _format_int(val)
    if val >= minimum:
        return label, value_str, "quality met", True
    return label, value_str, "strength low", False


def _summarize_pivot(value: Any, lower: float, upper: float) -> Tuple[str, str, str, bool]:
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


def _summarize_base_len(value: Any, minimum: float) -> Tuple[str, str, str, bool]:
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


def _summarize_relvol(value: Any, minimum: float, label: str = "RelVol") -> Tuple[str, str, str, bool]:
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


def _summarize_atr(value: Any, lower: float, upper: float) -> Tuple[str, str, str, bool]:
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


def _summarize_adx(value: Any, minimum: float) -> Tuple[str, str, str, bool]:
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


def _summarize_proximity(value: Any, minimum: float) -> Tuple[str, str, str, bool]:
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


def _summarize_day_change(value: Any, maximum: float, label: str = "day_change") -> Tuple[str, str, str, bool]:
    val = _maybe_float(value)
    if val is None:
        return label, "NA", "day change unknown", False
    value_str = _format_percent(val, include_sign=True)
    if val > maximum:
        return label, value_str, "too extended today", False
    if val >= 0:
        return label, value_str, "calm session", True
    return label, value_str, "pullback day", True


def _summarize_liquidity(value: Any, minimum: float) -> Tuple[str, str, str, bool]:
    val = _maybe_float(value)
    if val is None:
        return "liquidity", "NA", "liquidity unknown", False
    value_str = _format_liquidity(val)
    if val >= minimum:
        return "liquidity", value_str, "adequate liquidity", True
    return "liquidity", value_str, "thin liquidity", False


def _summarize_rsi(value: Any, lower: float, upper: float) -> Tuple[str, str, str, bool]:
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


def _summarize_adx_slope(value: Any) -> Tuple[str, str, str, bool]:
    if value is True:
        return "ADX_slope", "+", "trend strength rising", True
    if value is False:
        return "ADX_slope", "flat", "trend not improving", False
    return "ADX_slope", "NA", "trend slope unknown", False


def _summarize_persistence(value: Any) -> Tuple[str, str, str, bool]:
    if value is True:
        return "persistence", "Yes", "holding pivot/VWAP", True
    if value is False:
        return "persistence", "No", "lost pivot/VWAP", False
    return "persistence", "NA", "persistence unknown", False


def _compose_reason_string(items: List[Tuple[str, str, str]]) -> str:
    return " | ".join(f"{label}: {value} ({desc})" for label, value, desc in items if label)


def _build_eod_buy_metrics(row: Dict[str, Any]) -> Tuple[bool, List[Tuple[str, str, str]]]:
    reason_items: List[Tuple[str, str, str]] = []
    passed = True

    def add(metric: Tuple[str, str, str, bool], enforced: bool = True) -> None:
        nonlocal passed
        label, value_str, desc, ok = metric
        reason_items.append((label, value_str, desc))
        if enforced:
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


def _build_intraday_buy_metrics(row: Dict[str, Any]) -> Tuple[bool, List[Tuple[str, str, str]]]:
    reason_items: List[Tuple[str, str, str]] = []
    passed = True

    def add(metric: Tuple[str, str, str, bool], enforced: bool = True) -> None:
        nonlocal passed
        label, value_str, desc, ok = metric
        reason_items.append((label, value_str, desc))
        if enforced:
            passed = passed and bool(ok)

    # Provide baseline context that doesn't gate intraday BUY
    score_min = _threshold_float("breakout_score_min", 70.0)
    add(_summarize_score(row.get("score"), score_min), enforced=False)

    pivot_lo, pivot_hi = _threshold_range("breakout_pivot_clear_pct_range", (1.0, 5.0))
    add(_summarize_pivot(row.get("pivot_clear_pct"), pivot_lo, pivot_hi), enforced=False)

    base_len_min = _threshold_float("base_len_min_bars", 15.0)
    if base_len_min <= 0:
        base_len_min = 15.0
    add(_summarize_base_len(row.get("base_len_bars"), base_len_min), enforced=False)

    starter_score_min = _threshold_float("starter_score_min_intraday", 65.0)
    intraday_score = row.get("intraday_score")
    if intraday_score is None:
        intraday_score = row.get("score")
    add(_summarize_score(intraday_score, starter_score_min, label="starter_score"))

    relvol_source = row.get("intraday_relvol")
    if relvol_source is None:
        relvol_source = row.get("relvol20") if row.get("relvol20") is not None else row.get("vol_spike")
    relvol_min = _threshold_float("intraday_relvol_min", 1.5)
    add(_summarize_relvol(relvol_source, relvol_min), enforced=True)

    adx_min = _threshold_float("adx14_min", 22.0)
    add(_summarize_adx(row.get("adx") or row.get("adx14"), adx_min), enforced=True)

    add(_summarize_adx_slope(row.get("adx_slope_pos")), enforced=True)

    add(_summarize_rsi(row.get("rsi") or row.get("rsi14"), 58.0, 70.0), enforced=True)

    prox_min = _threshold_float("proximity_52w_min_pct", -8.0)
    prox_val = row.get("pct_from_52w_high") if row.get("pct_from_52w_high") is not None else row.get("proximity_52w_high_pct")
    add(_summarize_proximity(prox_val, prox_min), enforced=True)

    atr_lo, atr_hi = _threshold_range("atr10_pct_range", (3.0, 7.0))
    atr_val = row.get("atr10_pct") if row.get("atr10_pct") is not None else row.get("atr_pct")
    add(_summarize_atr(atr_val, atr_lo, atr_hi), enforced=True)

    day_cap = _threshold_float("day_change_cap_starter_pct", 4.0)
    day_val = row.get("change_pct") if row.get("change_pct") is not None else row.get("pct_today")
    add(_summarize_day_change(day_val, day_cap), enforced=True)

    liquidity_floor = _threshold_float("liquidity_floor_rupees", 5e7)
    liquidity_val = row.get("liquidity")
    if liquidity_val is None:
        liquidity_val = row.get("median_traded_value_20d")
    add(_summarize_liquidity(liquidity_val, liquidity_floor), enforced=True)

    add(_summarize_persistence(row.get("persistence_ok")), enforced=True)

    return passed, reason_items


def _evaluate_buy_gate(row: Dict[str, Any]) -> Tuple[str, str]:
    is_eod = bool(row.get("is_eod"))
    row["buy_mode"] = "EOD" if is_eod else "INTRADAY"
    passed, items = _build_eod_buy_metrics(row) if is_eod else _build_intraday_buy_metrics(row)
    reason = _compose_reason_string(items)
    return ("Yes" if passed else "No"), reason


def _make_scores_row(
    *,
    symbol: str,
    name: Optional[str],
    sector: Optional[str],
    as_of_iso: str,
    run_id: str,
    df: pd.DataFrame,
    ind: pd.DataFrame,
    breadth_hint: Optional[float] = None,
    regime_hint: Optional[str] = None,
    asm_hint: Optional[bool] = None,
    is_eod_snapshot: bool = False,
    persistence_history: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    persistence_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    # Build the final Screener row for this symbol (spec 2025-10-12A).
    last = float(df["close"].iloc[-1]) if not df.empty else None
    prev = float(df["close"].iloc[-2]) if len(df) >= 2 else None
    change_pct = ((last - prev) * 100.0 / prev) if (last is not None and prev not in (None, 0)) else None

    r = ind.iloc[-1].to_dict() if not ind.empty else {}
    rsi14 = _maybe_float(r.get("rsi14"))
    adx14 = _maybe_float(r.get("adx14"))
    relvol20 = _maybe_float(r.get("relvol20"))
    prox_52w = _maybe_float(r.get("proximity_52w_high_pct"))
    vol_z20 = _maybe_float(r.get("vol_z20"))
    atr10_pct = _maybe_float(r.get("atr10_pct"))
    obv_val = _maybe_float(r.get("obv"))
    obv_ma30 = _maybe_float(r.get("obv_ma30"))
    obv_slope_10 = _maybe_float(r.get("obv_slope_10"))
    obv_above_ma = (bool(r.get("obv_above_ma")) if r.get("obv_above_ma") is not None else None)
    pivot_high_20 = _maybe_float(r.get("pivot_high_20"))
    pivot_clear_pct = _maybe_float(r.get("pivot_clear_pct"))
    base_len_bars = _maybe_float(r.get("base_len_bars"))
    gap_up_pct = _maybe_float(r.get("gap_up_pct"))
    close_pos_in_bar = _maybe_float(r.get("close_pos_in_bar"))
    median_traded_value_20d = _maybe_float(r.get("median_traded_value_20d"))
    delivery_ratio_20d = _maybe_float(r.get("delivery_ratio_20d"))
    n_consecutive_up = _maybe_float(r.get("n_consecutive_up"))
    n_consecutive_down = _maybe_float(r.get("n_consecutive_down"))
    recent_failed_breakout_10d = bool(r.get("recent_failed_breakout_10d")) if r.get("recent_failed_breakout_10d") is not None else None
    adx_slope_pos = bool(r.get("adx_slope_pos")) if r.get("adx_slope_pos") is not None else None
    high_252 = _maybe_float(r.get("high_252"))
    ret_1w = _maybe_float(r.get("ret_1w"))
    ret_1m = _maybe_float(r.get("ret_1m"))
    ret_3m = _maybe_float(r.get("ret_3m"))
    ret_6m = _maybe_float(r.get("ret_6m"))
    ret_12_1m = _maybe_float(r.get("ret_12_1m"))
    ret_5d = _maybe_float(r.get("ret_5d"))
    ema10 = _maybe_float(r.get("ema10"))
    ema50 = _maybe_float(r.get("ema50"))
    ema200 = _maybe_float(r.get("ema200"))
    atr14_pct = _maybe_float(r.get("atr14_pct"))
    breadth_pct_50dma = breadth_hint if breadth_hint is not None else _maybe_float(r.get("breadth_pct_50dma"))
    nifty_regime_raw = regime_hint if regime_hint is not None else r.get("nifty_regime")
    nifty_regime = str(nifty_regime_raw).upper() if nifty_regime_raw else None
    mansfield_rs_52 = _maybe_float(r.get("mansfield_rs_52"))
    asm_gsm_flags = bool(asm_hint) if asm_hint is not None else (bool(r.get("asm_gsm_flags")) if r.get("asm_gsm_flags") is not None else False)
    upper_circuit_hits_60d = _count_upper_circuit_hits(df)

    score_inputs = {
        "proximity_52w_high_pct": prox_52w,
        "ret_5d": ret_5d if ret_5d is not None else ret_1w,
        "ret_1m": ret_1m,
        "ret_1w": ret_1w,
        "relvol20": relvol20,
        "vol_z20": vol_z20,
        "obv_above_ma": obv_above_ma,
        "obv_slope_10": obv_slope_10,
        "close": last,
        "ema10": ema10,
        "ema50": ema50,
        "ema200": ema200,
        "rsi14": rsi14,
        "adx14": adx14,
        "adx_slope_pos": adx_slope_pos,
        "mansfield_rs_52": mansfield_rs_52,
        "breadth_pct_50dma": breadth_pct_50dma,
        "delivery_ratio_20d": delivery_ratio_20d,
        "nifty_regime": nifty_regime,
        "gap_up_pct": gap_up_pct,
        "close_pos_in_bar": close_pos_in_bar,
        "pivot_clear_pct": pivot_clear_pct,
        "n_consecutive_up": n_consecutive_up,
        "n_consecutive_down": n_consecutive_down,
    }
    score_bundle = compute_score(score_inputs)

    score_bundle = compute_score(score_inputs)
    # domain.scoring returns score_basic on a 0..100 scale now.
    # Contract requires BOTH:
    # - score_basic (0..12 legacy)
    # - score_basic_normalized (0..100)
    score_basic_normalized = int(score_bundle.score_basic) if score_bundle.score_basic is not None else None
    score_basic = (
        int(round((score_basic_normalized / 100.0) * 12.0))
        if score_basic_normalized is not None
        else None
    )    
    score_full = score_bundle.score_full
    badges = score_bundle.badges or []

    full_required_keys = [
        "relvol20", "vol_z20", "obv", "obv_ma30", "obv_slope_10", "obv_above_ma",
        "pivot_high_20", "pivot_clear_pct", "base_len_bars",
        "proximity_52w_high_pct", "atr14_pct", "ema10", "ema50", "ema200", "rsi14", "adx14"
    ]
    data_gaps: List[str] = []
    for k in full_required_keys:
        v = r.get(k)
        missing = False
        try:
            missing = (v is None) or (isinstance(v, (float, np.floating)) and (np.isnan(v) or np.isinf(v)))
        except Exception:
            missing = v is None
        if missing:
            data_gaps.append(k)

    score_source = "full"
    stale = False
    if score_full is not None and not data_gaps:
        score = int(score_full)
    else:
        score = int(score_basic_normalized) if score_basic_normalized is not None else 0
        stale = True
        score_source = "basic_fallback" if score_full is None else "full_incomplete"

    if not badges:
        badges = [{"category": "WATCH", "label": "Watch (data incomplete)"}]

    reason_codes = list(score_bundle.reason_codes)
    if data_gaps:
        reason_codes.extend(f"missing:{gap}" for gap in sorted(set(data_gaps)))
    score_reason_codes = list(reason_codes)

    components = score_bundle.components
    score_breakdown = {
        "proximity": round(components.proximity, 2),
        "returns": round(components.returns, 2),
        "accumulation": round(components.accumulation, 2),
        "trend": round(components.trend, 2),
        "context": round(components.context, 2),
        "delivery_bonus": round(components.delivery_bonus, 2),
    }
    penalties_map = {k: round(v, 2) for k, v in components.penalties.items()}

    row: Dict[str, Any] = {
        "symbol": symbol,
        "name": name,
        "sector": sector,
        "last": last,
        "change_pct": change_pct,
        "rsi14": rsi14,
        "adx14": adx14,
        "ema10": ema10,
        "ema50": ema50,
        "ema200": ema200,
        "relvol20": relvol20,
        "relvol20_raw": _maybe_float(r.get("relvol20_raw")),
        "proximity_52w_high_pct": prox_52w,
        "atr14_pct": atr14_pct,
        "atr10_pct": atr10_pct,
        "vol_z20": vol_z20,
        "high_252": high_252,
        "obv": obv_val,
        "obv_ma30": obv_ma30,
        "obv_slope_10": obv_slope_10,
        "obv_above_ma": obv_above_ma,
        "pivot_high_20": pivot_high_20,
        "pivot_20d": pivot_high_20,
        "pivot_clear_pct": pivot_clear_pct,
        "base_len_bars": (int(round(base_len_bars)) if base_len_bars is not None else None),
        "gap_up_pct": gap_up_pct,
        "close_pos_in_bar": close_pos_in_bar,
        "median_traded_value_20d": median_traded_value_20d,
        "delivery_ratio_20d": delivery_ratio_20d,
        "n_consecutive_up": (int(n_consecutive_up) if n_consecutive_up is not None else None),
        "n_consecutive_down": (int(n_consecutive_down) if n_consecutive_down is not None else None),
        "recent_failed_breakout_10d": recent_failed_breakout_10d,
        "adx_slope_pos": adx_slope_pos,
        "ret_1w": ret_1w,
        "ret_5d": ret_5d,
        "ret_1m": ret_1m,
        "ret_3m": ret_3m,
        "ret_6m": ret_6m,
        "ret_12_1m": ret_12_1m,
        "breadth_pct_50dma": breadth_pct_50dma,
        "nifty_regime": nifty_regime,
        "mansfield_rs_52": mansfield_rs_52,
        "asm_gsm_flags": asm_gsm_flags,
        "upper_circuit_hits_60d": upper_circuit_hits_60d,
        "score": score,
        "score_full": score_full,
        "score_basic": score_basic,
        "score_basic_normalized": score_basic_normalized,
        "score_source": score_source,
        "data_gaps": data_gaps,
        "stale": stale,
        "rules_version": "2025-10-12A",
        "score_scale": "0-100",
        "badges": badges,
        "recommendation": "No",
        "buy": "No",
        "reason": score_bundle.band,
        "as_of": as_of_iso,
        "is_eod": bool(is_eod_snapshot),
        "run_id": run_id,
        "score_band": score_bundle.band,
        "reason_codes": score_reason_codes,
        "score_reason_codes": score_reason_codes,
        "score_breakdown": score_breakdown,
        "score_penalties": penalties_map,
        "score_components_raw": {
            "base": round(components.total_base(), 2),
            "with_context": round(components.total_with_context(), 2),
        },
    }

    row.setdefault("rsi", row.get("rsi14"))
    row.setdefault("adx", row.get("adx14"))
    row.setdefault("pct_from_52w_high", row.get("proximity_52w_high_pct"))
    row.setdefault("atr_pct", row.get("atr14_pct"))
    row.setdefault("pct_today", row.get("change_pct"))

    try:
        row["pre_gates_pass"] = global_pre_gates({**row, "close": row.get("last")})
    except Exception:
        row["pre_gates_pass"] = False

    try:
        next_action = compute_next_action(price=row.get("last"), indicators=row, position={})
    except Exception:
        next_action = {"code": "NONE"}
    next_action_code = str((next_action or {}).get("code") or "NONE").upper()
    next_action_reasons = list(next_action.get("reason_codes") or [])
    actionable = next_action_code in {"BUY_BREAKOUT", "BUY_PULLBACK", "BUY_STARTER"}

    regime_for_threshold = str(row.get("nifty_regime") or "").upper()
    min_score_required = 72 if regime_for_threshold == "DOWN" else 70
    score_value = row.get("score")
    meets_score = isinstance(score_value, (int, float)) and score_value >= min_score_required
    yes = bool(row.get("pre_gates_pass") and actionable and meets_score)

    row["recommendation"] = "Yes" if yes else "No"
    row["next_action"] = next_action_code
    row["next_action_code"] = next_action_code
    row["next_action_reason_codes"] = next_action_reasons

    combined_reason_codes = score_reason_codes[:]
    if next_action_code != "NONE":
        combined_reason_codes.append(f"next:{next_action_code}")
    combined_reason_codes.extend(next_action_reasons)
    combined_reason_codes = list(dict.fromkeys(combined_reason_codes))
    if combined_reason_codes:
        row["reason_codes"] = combined_reason_codes
        row["reason"] = " | ".join(combined_reason_codes[:6])
    else:
        row["reason_codes"] = score_reason_codes
        row["reason"] = score_bundle.band

    reason_before_buy = row.get("reason") or ""

    if row.get("liquidity") is None:
        try:
            ser_liq = (df["close"] * df["volume"]).rolling(20, min_periods=5).mean()
            row["liquidity"] = float(ser_liq.iloc[-1]) if ser_liq.notna().any() else None
        except Exception:
            row["liquidity"] = None

    if not is_eod_snapshot:
        history_snapshots = (persistence_history or {}).get(symbol, [])
        current_snapshot = _normalize_persistence_snapshot({**row, "symbol": symbol})
        if current_snapshot is not None and persistence_config:
            row["persistence_ok"] = _compute_persistence_ok(current_snapshot, history_snapshots, persistence_config)
        else:
            row["persistence_ok"] = False
    else:
        row.setdefault("persistence_ok", None)

    buy_flag, buy_reason = _evaluate_buy_gate(row)
    row["buy"] = buy_flag
    if buy_reason:
        row["reason"] = buy_reason
    else:
        row["reason"] = reason_before_buy

    if row.get("vol_spike") is None:
        try:
            if "vol_z20" in ind.columns:
                row["vol_spike"] = float(ind["vol_z20"].iloc[-1])
            else:
                v = df["volume"]
                mu = v.rolling(20, min_periods=5).mean()
                sd = v.rolling(20, min_periods=5).std(ddof=0)
                z = (v - mu) / sd.replace(0.0, np.nan)
                row["vol_spike"] = float(z.iloc[-1]) if z.notna().any() else None
        except Exception:
            row["vol_spike"] = None

    if not row.get("strength"):
        adx_val = row.get("adx")
        if isinstance(adx_val, (int, float)):
            row["strength"] = "High" if adx_val >= 35 else ("Medium" if adx_val >= 20 else "Low")

    badges_in: List[Any] = row.get("badges") or []
    badges_in = [b for b in badges_in if not (isinstance(b, dict) and b.get("category") == "ACTION")]
    badges_in.append({"category": "ACTION", "label": (next_action_code if yes else "Watch")})
    row["badges"] = badges_in

    cls_categories = {"BREAKOUT", "MOMENTUM", "WATCH", "IGNORE"}
    badge_remap = {
        "BAND": "MOMENTUM",
        "PRICE": "MOMENTUM",
        "VOLUME": "MOMENTUM",
        "TREND": "MOMENTUM",
        "INFO": "WATCH",
        "DATA": "WATCH",
    }

    def _code_to_category(code: str) -> Optional[str]:
        c = (code or "").upper()
        if "BREAKOUT" in c:
            return "BREAKOUT"
        if "MOMENTUM" in c:
            return "MOMENTUM"
        if "WATCH" in c:
            return "WATCH"
        if "IGNORE" in c:
            return "IGNORE"
        return None

    has_classification = any(
        isinstance(b, dict) and str(b.get("category", "")).upper() in cls_categories for b in badges_in
    )
    if not has_classification:
        if row["score"] is not None and row["score"] >= 85 and (rsi14 or 0) >= 60 and (adx14 or 0) >= 30 and (pivot_clear_pct or 0) >= 2.0:
            badges_in.append({"category": "BREAKOUT", "label": "Very High Breakout"})
        elif row["score"] is not None and row["score"] >= 75:
            badges_in.append({"category": "MOMENTUM", "label": "High Momentum"})
        else:
            badges_in.append({"category": "WATCH", "label": "Watch"})

    norm_badges: List[Dict[str, str]] = []
    for b in badges_in:
        if isinstance(b, dict):
            label = b.get("label") or b.get("text") or b.get("code") or "Badge"
            category = b.get("category")
            if not category:
                cat_from_code = _code_to_category(str(b.get("code", "")))
                category = cat_from_code or ""
            cat_upper = str(category or "").strip().upper()
            cat_upper = badge_remap.get(cat_upper, cat_upper)
            if cat_upper not in cls_categories and cat_upper != "ACTION":
                cat_upper = "WATCH"
            norm_badges.append({"category": cat_upper, "label": str(label).strip()})
        else:
            norm_badges.append({"category": "WATCH", "label": str(b).strip()})

    normalized_final: List[Dict[str, str]] = []
    for badge in norm_badges:
        cat = str((badge or {}).get("category") or "").strip().upper()
        lab = str((badge or {}).get("label") or "").strip()
        cat = badge_remap.get(cat, cat)
        if cat not in cls_categories and cat != "ACTION":
            cat = "WATCH"
        normalized_final.append({"category": cat, "label": lab})

    row["badges"] = normalized_final

    return row



# --------------------------- main orchestration -------------------------------

def run_screening(*, session: Session, key: Optional[str], payload: Dict[str, Any]) -> Tuple[RunDetail, bool]:
    """
    NEW: Write to the **new layout only** (no legacy to avoid confusion):
      * daily/as_of=YYYY-MM-DD/run_id=...
      * intraday/date=YYYY-MM-DD/run_id=...
    When as_of is provided, slice price history to <= as_of for correct EOD.
    """
    _ensure_parquet_root()
    jobs = SqlJobsRepo(session)
    history = SqlHistoryRepo(session)

    now_utc = _utcnow_aware()
    # ---- make as_of ISO **timezone-aware** ----
    as_of_raw = payload.get("as_of")
    as_of_date = _as_of_date_str(as_of_raw)
    if as_of_date:
        # represent EOD with midnight UTC to keep tz-aware
        as_of_iso = f"{as_of_date}T00:00:00Z"
    elif as_of_raw:
        # coerce any datetime-ish string to UTC ISO
        try:
            as_of_iso = pd.to_datetime(as_of_raw, utc=True).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            as_of_iso = now_utc.isoformat().replace("+00:00", "Z")
    else:
        as_of_iso = now_utc.isoformat().replace("+00:00", "Z")

    intraday_date_override: Optional[str] = None
    intraday_date_str: Optional[str] = None
    if not as_of_date:
        override_raw = payload.get("intraday_trading_date")
        intraday_date_override = _as_of_date_str(override_raw)
        intraday_date_str = intraday_date_override or now_utc.date().strftime("%Y-%m-%d")

    universe = None
    if isinstance(payload.get("universe"), str):
        uni = payload["universe"].strip().upper()
        universe = uni if uni in _ALLOWED_PRESETS else None

    # Daily backfills must bypass idempotency shortcuts so the parquet snapshot is always (re)written.
    if as_of_date:
        key_for_job = f"{key or 'BF_MANUAL'}::{as_of_date}::{uuid4().hex}"
    else:
        key_for_job = key
    job, created = jobs.create_or_get_by_key(name="manual_scan", key=key_for_job, with_created=True)

    if not created:
        status = str(job.status or "").upper()
        in_progress = status in {"RUNNING", "QUEUED", "IN_PROGRESS"}
        failed_status = status in {"FAILED", "CANCELLED", "ERROR"}
        snapshot_missing = (
            bool(as_of_date)
            and status == "SUCCEEDED"
            and _find_committed_run_for_as_of(as_of_date) is None
        )

        if failed_status or snapshot_missing:
            job.status = "RUNNING"
            job.started_at = datetime.utcnow()
            job.ended_at = None
            try:
                session.flush()
                session.commit()
            except Exception:
                session.rollback()
                raise
            created = True
            reason = "missing_snapshot" if snapshot_missing else "previous_failure"
            try:
                log.warning(
                    "screening_rerun_idempotent",
                    extra={
                        "run_id": job.run_id,
                        "key": key,
                        "reason": reason,
                        "as_of": as_of_date,
                        "status": status or "<none>",
                    },
                )
            except Exception:
                pass
        elif in_progress:
            return (
                RunDetail(
                    run_id=job.run_id,
                    job_name=getattr(job, "name", None),
                    status=job.status,
                    started_at=_to_aware(job.started_at),
                    ended_at=_to_aware(job.ended_at),
                    counts=Counts(symbols_processed=None, rows_written=None),
                    duration_ms=None,
                    key=getattr(job, "key", None),
                    snapshot_path=None,
                    error=None,
                    error_json=getattr(job, "error", None)
                    if isinstance(getattr(job, "error", None), dict)
                    else None,
                ),
                False,
            )
        else:
            # idempotent replay with completed snapshot: return prior run
            return (
                RunDetail(
                    run_id=job.run_id,
                    job_name=getattr(job, "name", None),
                    status=job.status,
                    started_at=_to_aware(job.started_at),
                    ended_at=_to_aware(job.ended_at),
                    counts=Counts(symbols_processed=None, rows_written=None),
                    duration_ms=None,
                    key=getattr(job, "key", None),
                    snapshot_path=None,
                    error=None,
                    error_json=getattr(job, "error", None)
                    if isinstance(getattr(job, "error", None), dict)
                    else None,
                ),
                False,
            )

    persistence_cfg: Optional[Dict[str, Any]] = None
    persistence_history: Dict[str, List[Dict[str, Any]]] = {}
    if not as_of_date:
        persistence_cfg = _resolve_persistence_config()
        bars_required = persistence_cfg.get("bars", 3) if persistence_cfg else 3
        try:
            persistence_history = _load_persistence_history(
                intraday_date_str,
                job.run_id,
                int(bars_required),
            )
        except Exception:
            persistence_history = {}

    symbols_processed = 0
    rows_written = 0
    snapshot_path = None

    try:
        cfg = app_config.load()
        is_eod_snapshot = _should_mark_eod_snapshot(
            now_utc=now_utc,
            as_of_date=as_of_date,
            intraday_trading_date=intraday_date_override,
            cfg=cfg,
        )
        try:
            log.info(
                "screening_snapshot_mode",
                extra={
                    "run_id": job.run_id,
                    "is_eod": is_eod_snapshot,
                    "as_of_date": as_of_date,
                    "intraday_trading_date": intraday_date_override,
                },
            )
        except Exception:
            pass
        resolved_universe = (
            (universe or "").strip().upper()
            or (getattr(cfg.scheduler, "universe", None) or "").strip().upper()
            or (getattr(cfg.screener, "default_universe", "NIFTY50") or "").strip().upper()
        )
        try:
            log.info("screening_start", extra={"run_id": job.run_id, "as_of": as_of_iso, "universe": resolved_universe})
        except Exception:
            pass

        # Load universe
        symbols, _ = UniverseRepo().list_symbols(resolved_universe, page=1, per_page=999_999)
        if not symbols:
            symbols = list(_FALLBACK_NSE)
        symbols_processed = len(symbols)
        try:
            log.info("screening_universe", extra={"count": symbols_processed, "sample": symbols[:5]})
        except Exception:
            pass

        # Name & sector via YahooAdapter (best-effort)
        ya = YahooAdapter()
        try:
            quotes = {q["symbol"]: q for q in (ya.fetch_quotes(symbols) or [])}
        except Exception:
            quotes = {}

        features_cfg = getattr(cfg, "features", {}) or {}
        momentum_features = features_cfg.get("momentum", {}) if isinstance(features_cfg, dict) else {}
        india_safety_cfg = momentum_features.get("india_safety", {}) if isinstance(momentum_features, dict) else {}
        asm_flag_symbols: set[str] = set()
        raw_asm_flags = india_safety_cfg.get("asm_gsm_symbols") if isinstance(india_safety_cfg, dict) else None
        if isinstance(raw_asm_flags, (list, tuple, set)):
            asm_flag_symbols = {str(s).upper() for s in raw_asm_flags}

        # Compute full rows
        prep_rows: List[Tuple[str, Dict[str, Any], pd.DataFrame, pd.DataFrame, bool]] = []
        breadth_total = 0
        breadth_above = 0
        for sym in symbols:
            df = _history_df(sym, period="400d")
            q = quotes.get(sym, {})

            # --- as_of slicing for EOD/backfills ---
            df_eff = df
            if as_of_date:
                try:
                    cut = pd.to_datetime(as_of_date).date()
                    if not df.empty:
                        mask = pd.Series(df.index.date <= cut, index=df.index)
                        df_eff = df.loc[mask[mask].index]
                except Exception:
                    df_eff = df  # fallback

            # --- skip symbols with no prices ---
            if df_eff is None or df_eff.empty:
                #log.warning("no prices for symbol; skipping row", extra={"symbol": sym, "as_of": as_of_iso})
                continue

            ind = _compute_indicators(df_eff)
            try:
                last_for_breadth = float(df_eff["close"].iloc[-1])
            except Exception:
                last_for_breadth = None
            try:
                ema50_for_breadth = float(ind["ema50"].iloc[-1])
            except Exception:
                ema50_for_breadth = None
            if last_for_breadth is not None and ema50_for_breadth is not None:
                breadth_total += 1
                if last_for_breadth >= ema50_for_breadth:
                    breadth_above += 1
            asm_flagged = sym.upper() in asm_flag_symbols
            prep_rows.append((sym, q, df_eff, ind, asm_flagged))

        breadth_pct = round((breadth_above * 100.0) / breadth_total, 2) if breadth_total else None
        nifty_regime_value = _resolve_nifty_regime(as_of_date)
        rows: List[Dict[str, Any]] = []
        for sym, q, df_eff, ind, asm_flag in prep_rows:
            row = _make_scores_row(
                symbol=sym,
                name=q.get("name"),
                sector=q.get("sector"),
                as_of_iso=as_of_iso,
                run_id=job.run_id,
                df=df_eff,
                ind=ind,
                breadth_hint=breadth_pct,
                regime_hint=nifty_regime_value,
                asm_hint=asm_flag,
                is_eod_snapshot=is_eod_snapshot,
                persistence_history=None if is_eod_snapshot else persistence_history,
                persistence_config=persistence_cfg,
            )
            if breadth_pct is not None:
                row["breadth_pct_50dma"] = breadth_pct
            if nifty_regime_value is not None:
                row["nifty_regime"] = nifty_regime_value
            elif not row.get("nifty_regime"):
                row["nifty_regime"] = "NEUTRAL"
            rows.append(row)

        rows_written = len(rows)
        try:
            log.info("scores_rows_built", extra={"rows": rows_written})
        except Exception:
            pass

        # ------------------- WRITE SNAPSHOTS (new layout only) -------------------
        datasets.write_schema_version("scores", 2)
        try:
            root = datasets.get_parquet_root().resolve()
        except Exception:
            root = None

        try:
            if as_of_date:
                # DAILY
                target = (root / "scores" / f"daily" / f"as_of={as_of_date}" / f"run_id={job.run_id}") if root else None
                log.info(
                    "scores_daily_precommit",
                    extra={"as_of": as_of_date, "run_id": job.run_id, "rows": rows_written, "target": str(target) if target else None}
                )
                w_daily = datasets.begin_atomic_write_scores_daily(as_of_date, job.run_id)
                # Detect immutable/no-op writer (from datasets) to avoid misleading logs/paths
                is_noop_daily = getattr(w_daily, "_closed", False) and not hasattr(w_daily, "tmp_dir")
                if is_noop_daily:
                    # Skip writing; point snapshot_path to existing committed run or the as_of dir
                    existing_rid = _find_committed_run_for_as_of(as_of_date)
                    if existing_rid:
                        snapshot_path = str((
                            datasets.get_parquet_root() / "scores" / "daily" / f"as_of={as_of_date}" / f"run_id={existing_rid}"
                        ).resolve())
                    else:
                        snapshot_path = str((
                            datasets.get_parquet_root() / "scores" / "daily" / f"as_of={as_of_date}"
                        ).resolve())
                    log.info(
                        "scores_daily_skip_immutable",
                        extra={"as_of": as_of_date, "existing_run_id": existing_rid, "snapshot_path": snapshot_path}
                    )
                else:
                    w_daily.write_df(pa.Table.from_pylist(rows))
                    w_daily.commit()
                    snapshot_path = str(
                        (datasets.get_parquet_root()
                         / "scores" / "daily"
                         / f"as_of={as_of_date}"
                         / f"run_id={job.run_id}").resolve()
                    )
                    # post-commit quick listing
                    try:
                        tgt = (datasets.get_parquet_root() / "scores" / "daily" / f"as_of={as_of_date}" / f"run_id={job.run_id}")
                        files = [p.name for p in tgt.glob("*.parquet")] if tgt.exists() else []
                        log.info("scores_daily_postcommit", extra={"target": str(tgt), "files": files})
                    except Exception:
                        pass
                    log.info("scores daily written", extra={"as_of": as_of_date, "run_id": job.run_id, "rows": rows_written})
            else:
                # INTRADAY
                intraday_date_str = intraday_date_override or _utcnow_aware().date().strftime("%Y-%m-%d")
                target = (root / "scores" / f"intraday" / f"date={intraday_date_str}" / f"run_id={job.run_id}") if root else None
                log.info(
                    "scores_intraday_precommit",
                    extra={
                        "date": intraday_date_str,
                        "run_id": job.run_id,
                        "rows": rows_written,
                        "target": str(target) if target else None,
                        "date_override": bool(intraday_date_override),
                    }
                )
                w_intra = datasets.begin_atomic_write_scores_intraday(intraday_date_str, job.run_id)
                w_intra.write_df(pa.Table.from_pylist(rows))
                w_intra.commit()
                snapshot_path = str(
                    (datasets.get_parquet_root()
                     / "scores" / "intraday"
                     / f"date={intraday_date_str}"
                     / f"run_id={job.run_id}").resolve()
                )
                # post-commit quick listing
                try:
                    tgt = (datasets.get_parquet_root() / "scores" / "intraday" / f"date={intraday_date_str}" / f"run_id={job.run_id}")
                    files = [p.name for p in tgt.glob("*.parquet")] if tgt.exists() else []
                    log.info("scores_intraday_postcommit", extra={"target": str(tgt), "files": files})
                except Exception:
                    pass
                log.info("scores intraday written", extra={"date": intraday_date_str, "run_id": job.run_id, "rows": rows_written})
        except Exception:
            log.exception("snapshot write failed", extra={"run_id": job.run_id})
            raise

        # ------------------- END WRITES -------------------

        # Mark success + write history (best-effort)
        jobs.complete_run(run_id=job.run_id, status="SUCCEEDED", error=None)
        try:
            history.insert_run_summary(run_id=job.run_id, as_of=as_of_iso, rows=rows_written)
        except Exception:
            pass

        return (
            RunDetail(
                run_id=job.run_id,
                job_name="manual_scan",
                status="SUCCEEDED",
                started_at=_to_aware(job.started_at),
                ended_at=_utcnow_aware(),
                counts=Counts(symbols_processed=symbols_processed, rows_written=rows_written),
                duration_ms=None,
                key=getattr(job, "key", None),
                snapshot_path=snapshot_path,
                error=None,
                error_json=None,
            ),
            True,
        )

    except StarletteHTTPException:
        jobs.fail_run(run_id=job.run_id, error="screening_service raised HTTPException")
        raise
    except Exception as exc:
        jobs.fail_run(run_id=job.run_id, error=f"screening_service failed: {exc}")
        raise StarletteHTTPException(
            status_code=500,
            detail={"code": "INTERNAL_ERROR", "detail": f"screening_service failed: {exc}"},
        )
