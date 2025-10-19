from __future__ import annotations
from typing import Any, Dict, Tuple
import logging
from .base import EvalContext

log = logging.getLogger(__name__)

def _in_range(v: float | None, rng: Tuple[float, float]) -> bool:
    if v is None:
        return False
    lo, hi = rng
    return (lo is None or v >= lo) and (hi is None or v <= hi)

def passes_filters(ctx: EvalContext, symbol: str, item_filters: Dict[str, Any]) -> tuple[bool, Dict[str, Any]]:
    """
    Interprets YAML 'filters' by pulling metrics via ctx.metric(symbol, name).
    Only evaluates keys that exist in YAML; missing metrics => filter fails.
    Returns (passed, capture) where capture is a dict of values for templating.
    """
    cap: Dict[str, Any] = {"symbol": symbol}
    log.debug("Evaluating filters for symbol=%s keys=%s", symbol, list(item_filters.keys()))

    for key, val in item_filters.items():
        # Score filters
        if key == "score_min":
            score = ctx.metric(symbol, "score")
            cap["score"] = score
            if score is None or score < float(val):
                log.debug("Filter score_min failed symbol=%s value=%s threshold=%s", symbol, score, val)
                return False, cap

        elif key == "score_max":
            score = ctx.metric(symbol, "score")
            cap["score"] = score
            if score is None or score > float(val):
                log.debug("Filter score_max failed symbol=%s value=%s threshold=%s", symbol, score, val)
                return False, cap

        elif key == "intraday_score_min":
            s = ctx.metric(symbol, "intraday_score")
            cap["score"] = s
            if s is None or s < float(val):
                log.debug("Filter intraday_score_min failed symbol=%s value=%s threshold=%s", symbol, s, val)
                return False, cap

        # Ranges
        elif key == "atr10_pct_range":
            atr10 = ctx.metric(symbol, "atr10_pct")
            cap["atr10_pct"] = atr10
            if not _in_range(atr10, (float(val[0]), float(val[1]))):
                log.debug("Filter atr10_pct_range failed symbol=%s value=%s range=%s", symbol, atr10, val)
                return False, cap

        elif key == "pivot_clear_pct_range":
            pct = ctx.metric(symbol, "pivot_clear_pct")
            cap["pivot_clear_pct"] = pct
            if not _in_range(pct, (float(val[0]), float(val[1]))):
                log.debug("Filter pivot_clear_pct_range failed symbol=%s value=%s range=%s", symbol, pct, val)
                return False, cap

        # Liquidity / relvol
        elif key == "liquidity_floor_rupees":
            liq = ctx.metric(symbol, "avg_turnover_20d")
            cap["avg_turnover_20d"] = liq
            if liq is None or liq < float(val):
                log.debug("Filter liquidity_floor_rupees failed symbol=%s value=%s threshold=%s", symbol, liq, val)
                return False, cap

        elif key == "relvol20_min":
            rv = ctx.metric(symbol, "relvol20")
            cap["relvol20"] = rv
            if rv is None or rv < float(val):
                log.debug("Filter relvol20_min failed symbol=%s value=%s threshold=%s", symbol, rv, val)
                return False, cap

        elif key == "pullback_relvol20_min":
            rv = ctx.metric(symbol, "relvol20")
            cap["relvol20"] = rv
            if rv is None or rv < float(val):
                log.debug("Filter pullback_relvol20_min failed symbol=%s value=%s threshold=%s", symbol, rv, val)
                return False, cap

        elif key == "intraday_relvol_min":
            rv = ctx.metric(symbol, "intraday_relvol")
            cap["intraday_relvol"] = rv
            if rv is None or rv < float(val):
                log.debug("Filter intraday_relvol_min failed symbol=%s value=%s threshold=%s", symbol, rv, val)
                return False, cap

        # Position in bar / day change
        elif key in ("min_close_pos_in_bar", "strong_close_min_pos_in_bar"):
            pos = ctx.metric(symbol, "close_pos_in_bar")
            cap["close_pos_in_bar"] = pos
            if pos is None or pos < float(val):
                log.debug("Filter %s failed symbol=%s value=%s threshold=%s", key, symbol, pos, val)
                return False, cap

        elif key == "max_close_pos_in_bar":
            pos = ctx.metric(symbol, "close_pos_in_bar")
            cap["close_pos_in_bar"] = pos
            if pos is None or pos > float(val):
                log.debug("Filter max_close_pos_in_bar failed symbol=%s value=%s threshold=%s", symbol, pos, val)
                return False, cap

        elif key == "day_change_max_pct":
            ch = ctx.metric(symbol, "day_change_pct")
            cap["day_change_pct"] = ch
            if ch is None or ch > float(val):
                log.debug("Filter day_change_max_pct failed symbol=%s value=%s threshold=%s", symbol, ch, val)
                return False, cap

        # Trend/ADX/RSI
        elif key == "adx14_min":
            adx = ctx.metric(symbol, "adx14")
            cap["adx14"] = adx
            if adx is None or adx < float(val):
                log.debug("Filter adx14_min failed symbol=%s value=%s threshold=%s", symbol, adx, val)
                return False, cap

        elif key == "adx14_rising":
            if val:
                rising = ctx.metric(symbol, "adx14_rising")
                cap["adx14_rising"] = rising
                if rising is not True:
                    log.debug("Filter adx14_rising failed symbol=%s value=%s", symbol, rising)
                    return False, cap

        elif key == "rsi14_range":
            rsi = ctx.metric(symbol, "rsi14")
            cap["rsi14"] = rsi
            lo, hi = float(val[0]), float(val[1])
            if rsi is None or not (lo <= rsi <= hi):
                log.debug("Filter rsi14_range failed symbol=%s value=%s range=%s", symbol, rsi, val)
                return False, cap

        # 52-wk proximity
        elif key == "proximity_52w_min_pct":
            prox = ctx.metric(symbol, "prox_52w_pct")
            cap["prox_52w_pct"] = prox
            if prox is None or prox < float(val):
                log.debug("Filter proximity_52w_min_pct failed symbol=%s value=%s threshold=%s", symbol, prox, val)
                return False, cap

        # Pattern/structure
        elif key == "base_len_bars_min":
            bl = ctx.metric(symbol, "base_len_bars")
            cap["base_len_bars"] = bl
            if bl is None or bl < int(val):
                log.debug("Filter base_len_bars_min failed symbol=%s value=%s threshold=%s", symbol, bl, val)
                return False, cap

        elif key == "requires_extended_recent":
            if val:
                ext = ctx.metric(symbol, "extended_recent")  # e.g., rsi>70 or prior pivot_clear>3%
                cap["extended_recent"] = ext
                if not ext:
                    log.debug("Filter requires_extended_recent failed symbol=%s value=%s", symbol, ext)
                    return False, cap

        elif key == "ema10_pullback_zone":
            in_zone = ctx.metric(symbol, "ema10_pullback_zone")
            cap["ema10_pullback_zone"] = in_zone
            if in_zone is not True:
                log.debug("Filter ema10_pullback_zone failed symbol=%s value=%s", symbol, in_zone)
                return False, cap

        # Position filters
        elif key == "for_active_positions_only":
            active = ctx.metric(symbol, "has_position")
            cap["has_position"] = active
            if active is not True:
                log.debug("Filter for_active_positions_only failed symbol=%s value=%s", symbol, active)
                return False, cap

        elif key == "price_above_method_line":
            ok = ctx.metric(symbol, "price_above_method_line")
            cap["price_above_method_line"] = ok
            if ok is not True:
                log.debug("Filter price_above_method_line failed symbol=%s value=%s", symbol, ok)
                return False, cap

        elif key == "within_pct_below_method_line":
            d = ctx.metric(symbol, "pct_below_method_line")
            cap["pct_below_method_line"] = d
            if d is None or d > float(val):
                log.debug("Filter within_pct_below_method_line failed symbol=%s value=%s threshold=%s", symbol, d, val)
                return False, cap

        elif key == "stop_violated":
            stop_hit = ctx.metric(symbol, "stop_violated")
            cap["stop_violated"] = stop_hit
            if stop_hit is not True:
                log.debug("Filter stop_violated failed symbol=%s value=%s", symbol, stop_hit)
                return False, cap

        elif key == "consecutive_closes_below_method_line":
            n = ctx.metric(symbol, "consecutive_closes_below_method_line")
            cap["consecutive_closes_below_method_line"] = n
            if n is None or n < int(val):
                log.debug("Filter consecutive_closes_below_method_line failed symbol=%s value=%s threshold=%s", symbol, n, val)
                return False, cap

        elif key == "breakout_yesterday":
            b = ctx.metric(symbol, "breakout_yday")
            cap["breakout_yday"] = b
            if b is not True:
                log.debug("Filter breakout_yesterday failed symbol=%s value=%s", symbol, b)
                return False, cap

        elif key == "close_below_pivot_today":
            b = ctx.metric(symbol, "close_below_pivot_today")
            cap["close_below_pivot_today"] = b
            if b is not True:
                log.debug("Filter close_below_pivot_today failed symbol=%s value=%s", symbol, b)
                return False, cap

        elif key == "unrealized_gain_min_pct":
            g = ctx.metric(symbol, "unrealized_gain_pct")
            cap["unrealized_gain_pct"] = g
            if g is None or g < float(val):
                log.debug("Filter unrealized_gain_min_pct failed symbol=%s value=%s threshold=%s", symbol, g, val)
                return False, cap

        elif key == "days_since_entry_min":
            d = ctx.metric(symbol, "days_since_entry")
            cap["days_since_entry"] = d
            if d is None or d < int(val):
                log.debug("Filter days_since_entry_min failed symbol=%s value=%s threshold=%s", symbol, d, val)
                return False, cap

        elif key == "gain_max_pct":
            g = ctx.metric(symbol, "gain_pct")
            cap["gain_pct"] = g
            if g is None or g > float(val):
                log.debug("Filter gain_max_pct failed symbol=%s value=%s threshold=%s", symbol, g, val)
                return False, cap

        elif key == "score_max":
            s = ctx.metric(symbol, "score")
            cap["score"] = s
            if s is None or s > float(val):
                log.debug("Filter score_max failed symbol=%s value=%s threshold=%s", symbol, s, val)
                return False, cap

        elif key == "next_action_in":
            na = ctx.metric(symbol, "next_action_code")
            cap["next_action_code"] = na
            if na not in list(val):
                log.debug("Filter next_action_in failed symbol=%s value=%s allowed=%s", symbol, na, val)
                return False, cap

        # Intraday persistence block
        elif key == "persistence_bars":
            cfg = dict(val or {})
            bars = int(cfg.get("bars", 0))
            ok = bars > 0 and ctx.metric(symbol, "persistence_ok")
            cap["persistence_ok"] = ok
            if ok is not True:
                log.debug("Filter persistence_bars failed symbol=%s bars=%s persistence_ok=%s", symbol, bars, ok)
                return False, cap

        else:
            # Unknown filter key => fail fast to avoid silent nonsense
            log.warning("Unknown filter key=%s symbol=%s", key, symbol)
            return False, cap

    log.debug("Filters passed for symbol=%s capture=%s", symbol, cap)
    return True, cap
