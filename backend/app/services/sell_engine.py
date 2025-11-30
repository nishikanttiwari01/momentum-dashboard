from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from app.alerts.types import Mode
from app.core.config import StrategyConfig
from app.domain.indicators import atr
from app.repos.sql.positions_repo import PositionsRepo


@dataclass
class SellEvent:
    event_code: str
    symbol: str
    context: Dict[str, Any]
    score_at_fire: Optional[float] = None


def _safe_float(value: Any) -> Optional[float]:
    if value in (None, "", "None"):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f:
        return None
    return f


def _parse_note(note: Optional[str]) -> Dict[str, Any]:
    if not note:
        return {}
    try:
        parsed = json.loads(note)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return {}


def _dump_note(note: Dict[str, Any]) -> str:
    try:
        return json.dumps(note, separators=(",", ":"), default=str)
    except Exception:
        return json.dumps({})


def _compute_trailing_stop(
    df: pd.DataFrame,
    *,
    lookback: int,
    atr_period: int,
    atr_multiple: float,
) -> Optional[float]:
    if df is None or df.empty:
        return None
    highs = pd.to_numeric(df["high"], errors="coerce")
    lows = pd.to_numeric(df["low"], errors="coerce")
    closes = pd.to_numeric(df["close"], errors="coerce")
    if highs.isna().all() or lows.isna().all() or closes.isna().all():
        return None
    lookback = max(1, int(lookback))
    atr_period = max(1, int(atr_period))
    recent_high = highs.tail(lookback).max()
    atr_series = atr(highs, lows, closes, atr_period)
    atr_value = _safe_float(atr_series.iloc[-1] if not atr_series.empty else None)
    if atr_value is None or recent_high is None:
        return None
    return recent_high - float(atr_multiple) * atr_value


def evaluate_positions(
    *,
    session,
    rows_by_symbol: Dict[str, Dict[str, Any]],
    frames_by_symbol: Dict[str, Tuple[pd.DataFrame, pd.DataFrame]],
    strategy: StrategyConfig,
    mode: Mode,
    trading_day: date,
    now_utc: datetime,
) -> List[SellEvent]:
    repo = PositionsRepo(session)
    active_positions = repo.list_positions(active=True)
    if not active_positions:
        return []

    sell_cfg = strategy.profiles.sell.common
    events: List[SellEvent] = []

    for pos in active_positions:
        symbol_raw = pos.get("symbol")
        if not symbol_raw:
            continue
        symbol = str(symbol_raw).upper()
        row = rows_by_symbol.get(symbol)
        if not row:
            continue
        frame_tuple = frames_by_symbol.get(symbol)
        df_prices = frame_tuple[0] if frame_tuple else None

        price_now = _safe_float(row.get("last"))
        entry_price = _safe_float(pos.get("entry_price_locked"))
        if price_now is None or entry_price is None or entry_price <= 0:
            continue

        is_candidate_pool_member = bool(row.get("candidate_pool_member"))

        note_data = _parse_note(pos.get("note"))
        breakeven_active = bool(pos.get("breakeven_active"))
        prev_stop = _safe_float(pos.get("stop_now"))

        atr_multiple = sell_cfg.stop.atr_multiple_euphoria if pos.get("euphoria_on") else sell_cfg.stop.atr_multiple
        new_stop = _compute_trailing_stop(
            df_prices,
            lookback=sell_cfg.stop.lookback_bars,
            atr_period=sell_cfg.stop.atr_period,
            atr_multiple=atr_multiple,
        )
        if new_stop is not None and sell_cfg.stop.floor_pct is not None:
            floor_price = price_now * (1 - float(sell_cfg.stop.floor_pct) / 100.0)
            new_stop = max(new_stop, floor_price)

        if new_stop is None or new_stop <= 0:
            new_stop = prev_stop

        pnl_pct = None
        if entry_price:
            pnl_pct = ((price_now - entry_price) / entry_price) * 100.0

        t1_hit = bool(note_data.get("t1_hit"))
        t2_hit = bool(note_data.get("t2_hit"))
        breakeven_triggered = bool(note_data.get("breakeven_triggered"))

        targets_cfg = sell_cfg.targets
        t1_price = entry_price * (1 + float(targets_cfg.t1_gain_pct) / 100.0)
        t2_price = entry_price * (1 + float(targets_cfg.t2_gain_pct) / 100.0)

        event_code: Optional[str] = None
        event_context: Dict[str, Any] = {}

        stop_check_price = new_stop if new_stop is not None else prev_stop
        stop_condition = stop_check_price is not None and price_now <= stop_check_price

        timeout_cfg = sell_cfg.timeout
        created_at = pos.get("created_at")
        days_since_entry = None
        if isinstance(created_at, datetime):
            days_since_entry = (trading_day - created_at.date()).days

        timeout_condition = (
            timeout_cfg.enabled
            and timeout_cfg.max_holding_days is not None
            and days_since_entry is not None
            and days_since_entry >= int(timeout_cfg.max_holding_days)
            and (not timeout_cfg.eod_only or mode == Mode.EOD)
        )

        failed_cfg = sell_cfg.failed_breakout
        pivot_price = _safe_float(row.get("pivot_high_20"))
        relvol_down = _safe_float(row.get("relvol20"))
        failed_condition = (
            failed_cfg.enabled
            and pivot_price is not None
            and price_now < pivot_price
            and (relvol_down or 0) >= (failed_cfg.relvol_down_min or 0)
            and (not failed_cfg.eod_only or mode == Mode.EOD)
            and not is_candidate_pool_member  # don't alert failed breakout for pool members
        )

        breakeven_cfg = sell_cfg.breakeven
        breakeven_allowed_now = (
            breakeven_cfg.enabled
            and (mode == Mode.EOD or breakeven_cfg.intraday_enabled)
        )
        if not breakeven_active and breakeven_allowed_now:
            gain_threshold = entry_price * (1 + float(breakeven_cfg.gain_pct) / 100.0)
            if price_now >= gain_threshold:
                breakeven_active = True
                note_data["breakeven_armed_at"] = now_utc.isoformat()

        breakeven_condition = False
        if breakeven_active and breakeven_allowed_now and not breakeven_triggered:
            retrace_pct = float(breakeven_cfg.retrace_to_pct or 0)
            retrace_price = entry_price * (1 + retrace_pct)
            if price_now <= retrace_price:
                breakeven_condition = True
                breakeven_active = False
                note_data["breakeven_triggered"] = True

        targets_cfg = sell_cfg.targets
        allow_intraday_targets = targets_cfg.allow_intraday or mode == Mode.EOD
        t2_condition = allow_intraday_targets and price_now >= t2_price and not t2_hit
        t1_condition = allow_intraday_targets and price_now >= t1_price and not t1_hit

        weak_cfg = sell_cfg.weakness
        ema_fast = _safe_float(row.get("ema10") if weak_cfg.fast_ema_period == 10 else row.get(f"ema{weak_cfg.fast_ema_period}"))
        weakness_condition = (
            weak_cfg.enabled
            and (not weak_cfg.eod_only or mode == Mode.EOD)
            and ema_fast is not None
            and price_now < ema_fast
            and row.get("n_consecutive_down") is not None
            and int(row.get("n_consecutive_down")) >= int(weak_cfg.max_closes_below_fast_ema)
            and (row.get("relvol20") or 0) >= (weak_cfg.confirm_relvol_min or 0)
        )

        trail_update = False
        if new_stop is not None and prev_stop is not None:
            trail_update = new_stop > prev_stop and not stop_condition
        elif new_stop is not None and prev_stop is None:
            trail_update = True

        # Priority resolution
        if stop_condition:
            event_code = "SELL_STOP"
            event_context = {
                "symbol": symbol,
                "price": price_now,
                "stop": stop_check_price,
                "pnl_pct": pnl_pct,
                "entry_price": entry_price,
                "stop_method": pos.get("stop_method")
                or getattr(sell_cfg.stop, "method", None),
            }
        elif failed_condition:
            event_code = "SELL_FAILED_BREAKOUT"
            event_context = {
                "symbol": symbol,
                "price": price_now,
                "pivot": pivot_price,
                "relvol_down": relvol_down,
                "entry_price": entry_price,
                "pnl_pct": pnl_pct,
            }
        elif timeout_condition:
            event_code = "SELL_TIMEOUT"
            event_context = {
                "symbol": symbol,
                "price": price_now,
                "days_since_entry": days_since_entry,
                "entry_price": entry_price,
                "pnl_pct": pnl_pct,
            }
        elif t2_condition:
            event_code = "SELL_TARGET_T2"
            event_context = {
                "symbol": symbol,
                "price": price_now,
                "target": t2_price,
                "entry_price": entry_price,
                "pnl_pct": pnl_pct,
                "t2": targets_cfg.t2_gain_pct,
            }
            note_data["t2_hit"] = True
        elif t1_condition:
            event_code = "SELL_TARGET_T1"
            event_context = {
                "symbol": symbol,
                "price": price_now,
                "target": t1_price,
                "entry_price": entry_price,
                "pnl_pct": pnl_pct,
                "t1": targets_cfg.t1_gain_pct,
            }
            note_data["t1_hit"] = True
        elif breakeven_condition:
            event_code = "SELL_BREAKEVEN"
            event_context = {
                "symbol": symbol,
                "price": price_now,
                "entry_price": entry_price,
                "pnl_pct": pnl_pct,
            }
        elif weakness_condition:
            event_code = "SELL_WEAKNESS"
            event_context = {
                "symbol": symbol,
                "price": price_now,
                "ema": ema_fast,
                "relvol": row.get("relvol20"),
                "entry_price": entry_price,
                "pnl_pct": pnl_pct,
            }
        elif trail_update and new_stop is not None and sell_cfg.trail_update.route_alerts:
            event_code = "SELL_TRAIL_UPDATE"
            event_context = {
                "symbol": symbol,
                "stop": new_stop,
                "previous_stop": prev_stop,
            }

        updated_fields: Dict[str, Any] = {}
        if new_stop is not None and new_stop != prev_stop:
            updated_fields["stop_now"] = new_stop
        updated_fields["breakeven_active"] = breakeven_active
        updated_fields["note"] = _dump_note(note_data)

        if updated_fields:
            repo.update_by_id(pos["id"], **updated_fields)

        if event_code:
            context_payload = {
                **event_context,
                "run_id": row.get("run_id"),
                "as_of": row.get("as_of"),
            }
            events.append(
                SellEvent(
                    event_code=event_code,
                    symbol=symbol,
                    context=context_payload,
                    score_at_fire=_safe_float(row.get("score")),
                )
            )

    return events
