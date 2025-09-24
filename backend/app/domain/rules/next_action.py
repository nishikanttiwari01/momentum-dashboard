# backend/app/domain/next_action.py
from __future__ import annotations
from typing import Any, Dict, List, Tuple, Optional
import logging

log = logging.getLogger("app.domain.next_action")

def _fmt_price(x: Optional[float]) -> str:
    try:
        return f"{float(x):.2f}"
    except Exception:
        return "—"

def _bool(x: Any) -> bool:
    return bool(x) if x is not None else False

def _euphoria_on(ind: Dict[str, Any]) -> bool:
    rsi = ind.get("rsi14")
    adx = ind.get("adx14")
    adx_slope_5 = ind.get("adx_slope_5") or 0
    try:
        rsi = float(rsi) if rsi is not None else None
        adx = float(adx) if adx is not None else None
    except Exception:
        return False
    if rsi is None or adx is None:
        return False
    return (rsi >= 75 and adx >= 30) or (rsi >= 70 and adx >= 25 and adx_slope_5 > 0)

def _breakeven_active(pos: Dict[str, Any], price: Optional[float]) -> bool:
    entry = pos.get("entry_price_locked")
    stop_now = pos.get("stop_now")
    try:
        entry_f = float(entry) if entry is not None else None
        stop_f = float(stop_now) if stop_now is not None else None
        price_f = float(price) if price is not None else None
    except Exception:
        entry_f = stop_f = price_f = None
    if entry_f is None:
        return False
    if stop_f is not None and stop_f >= entry_f:
        return True

    return False

def _exit_close_threshold(ind: Dict[str, Any], eup_on: bool) -> Optional[float]:
    """
    Exit at close if Close < EMA{n}, where n = 10 normally, 8 if euphoria.
    Accept either explicit EMA fields or fall back to 'ema_slow_value' if needed.
    """
    if eup_on:
        val = ind.get("ema8") or ind.get("ema_8")
        if val is not None:
            try:
                return float(val)
            except Exception:
                pass
    # default to EMA10
    val = ind.get("ema10") or ind.get("ema_10") or ind.get("ema_slow_value")
    try:
        return float(val) if val is not None else None
    except Exception:
        return None

def _in_position(pos: Dict[str, Any]) -> bool:
    return pos.get("entry_price_locked") is not None

def _prefilter_ignore(ind: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Hard blocks: too volatile, illiquid, or explicitly flagged.
    - Volatility: ATR14% > 8
    - Liquidity: turnover_cr (if present) < 10
    - Any explicit block flag (e.g., 'blocked_reason')
    """
    atr = ind.get("atr14_pct")
    turnover = ind.get("turnover_cr")  # optional if you compute it
    blocked = ind.get("blocked_reason")
    try:
        if atr is not None and float(atr) > 8.0:
            return True, "Too volatile (ATR%)"
    except Exception:
        pass
    try:
        if turnover is not None and float(turnover) < 10.0:
            return True, "Illiquid"
    except Exception:
        pass
    if blocked:
        return True, str(blocked)
    return False, ""

def _gateway_breakout(ind: Dict[str, Any]) -> bool:
    """
    Gateway for a clean breakout entry.
    score>=70, ADX>=25, RelVol>=1.5, proximity to 52W high not deeply negative.
    """
    score = ind.get("score")
    adx = ind.get("adx14")
    relvol = ind.get("relvol20")
    prox = ind.get("proximity_52w_high_pct")
    try:
        s_ok = score is not None and float(score) >= 70.0
    except Exception:
        s_ok = False
    try:
        a_ok = adx is not None and float(adx) >= 25.0
    except Exception:
        a_ok = False
    try:
        v_ok = relvol is not None and float(relvol) >= 1.5
    except Exception:
        v_ok = False
    try:
        p_ok = prox is None or float(prox) >= -7.0
    except Exception:
        p_ok = False
    return s_ok and a_ok and v_ok and p_ok

def _extended_over_pivot(ind: Dict[str, Any]) -> bool:
    """
    Consider extension if pivot_clear_pct > +5%.
    """
    pc = ind.get("pivot_clear_pct")
    try:
        return pc is not None and float(pc) > 5.0
    except Exception:
        return False

def _pullback_zone(ind: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    """
    Suggested pullback zone near EMA10 with ATR buffer.
    """
    ema10 = ind.get("ema10") or ind.get("ema_10")
    atr10_pct = ind.get("atr10_pct")
    try:
        e = float(ema10) if ema10 is not None else None
        a10 = float(atr10_pct) if atr10_pct is not None else None
    except Exception:
        e = a10 = None
    if e is None or a10 is None:
        return None, None
    # translate ATR% to absolute approx using current price context if available
    px = ind.get("price")  # allow caller to pass price also inside indicators
    try:
        px = float(px) if px is not None else None
    except Exception:
        px = None
    if px is None:
        # use EMA as proxy for price if price not provided
        px = e
    atr_abs = px * (a10 / 100.0)
    low = e - 0.5 * atr_abs
    high = e
    return low, high

def _gates_failed(ind: Dict[str, Any]) -> List[str]:
    """
    Soft gates that decide WATCH for non-positions:
    - score < 35
    - relvol20 < 0.8
    - proximity to 52W high < -10%
    - pivot_clear_pct < 0
    - base_len_bars < 15
    - adx14 < 22
    """
    reasons: List[str] = []
    def _f(x): 
        try: return float(x)
        except Exception: return None

    score = _f(ind.get("score"))
    if score is None or score < 35: reasons.append("score<35")

    relvol = _f(ind.get("relvol20"))
    if relvol is None or relvol < 0.8: reasons.append("relvol20<0.8")

    prox = _f(ind.get("proximity_52w_high_pct"))
    if prox is not None and prox < -10.0: reasons.append("far_from_52w")

    pivot_clear = _f(ind.get("pivot_clear_pct"))
    if pivot_clear is not None and pivot_clear < 0.0: reasons.append("pivot_not_cleared")

    base_len = ind.get("base_len_bars")
    try:
        if int(base_len or 0) < 15:
            reasons.append("base_len<15")
    except Exception:
        reasons.append("base_len<15")

    adx = _f(ind.get("adx14"))
    if adx is None or adx < 22.0: reasons.append("adx<22")

    return reasons

def compute_next_action(*, price: float | None, indicators: Dict[str, Any], position: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deterministic resolver with priority:
    1) SELL_NOW (stop touched intraday)
    2) SELL_TOMORROW (EOD: close < exit threshold)
    3) In-position holds: HOLD_TIGHT (euphoria) / HOLD_BREAKEVEN / HOLD
    4) Entries when not in position: BUY_BREAKOUT / BUY_PULLBACK / BUY_STARTER
    5) Else: WATCH; prefilter blocks: IGNORE
    """
    # Backward-compatible refs used by your FE
    ema_n = indicators.get("ema_slow") or 10
    ema_val = indicators.get("ema_slow_value")
    stop_now = position.get("stop_now")
    entry_locked = position.get("entry_price_locked")
    qty = position.get("qty")

    # Enrich indicators with price for helper usage
    if price is not None:
        indicators.setdefault("price", price)

    eup_on = _euphoria_on(indicators)
    exit_threshold = _exit_close_threshold(indicators, eup_on)

    # Log snapshot of inputs
    log.debug(
        "next_action inputs | price=%s entry_locked=%s stop_now=%s eup=%s ema_val=%s score=%s relvol20=%s adx14=%s prox52w=%s pivot_clear=%s base_len=%s",
        price, entry_locked, stop_now, eup_on, exit_threshold,
        indicators.get("score"), indicators.get("relvol20"), indicators.get("adx14"),
        indicators.get("proximity_52w_high_pct"), indicators.get("pivot_clear_pct"), indicators.get("base_len_bars")
    )

    # ---------- 0) Hard prefilters (only if NOT already in a trade) ----------
    in_pos = _in_position(position)
    if not in_pos:
        blocked, why = _prefilter_ignore(indicators)
        if blocked:
            msg = f"Ignore — does not meet basic filters ({why})"
            log.info("next_action=IGNORE reason=%s", why)
            return {
                "code": "IGNORE",
                "text": msg,
                "reasons": [why],
                "refs": {"stop_now": stop_now, "ema_n": ema_n, "ema_value": ema_val, "exit_close_threshold": exit_threshold}
            }

    # ---------- 1) SELL_NOW (intraday stop touched) ----------
    # ✅ Only when in position
    if in_pos and price is not None and stop_now is not None:
        try:
            if float(price) <= float(stop_now):
                msg = f"Sell now (stop hit at ₹{_fmt_price(stop_now)})"
                log.info("next_action=SELL_NOW price<=stop stop=%s", _fmt_price(stop_now))
                return {
                    "code": "SELL_NOW",
                    "text": msg,
                    "reasons": ["price<=stop_now"],
                    "refs": {"stop_now": stop_now, "ema_n": ema_n, "ema_value": ema_val, "exit_close_threshold": exit_threshold}
                }
        except Exception as e:
            log.exception("SELL_NOW check failed: %s", e)

    # ---------- 2) SELL_TOMORROW (EOD close < threshold) ----------
    # ✅ Only when in position; only when bar is complete
    is_eod = _bool(indicators.get("is_eod")) or _bool(indicators.get("market_closed"))
    if in_pos and is_eod and price is not None and exit_threshold is not None:
        try:
            if float(price) < float(exit_threshold):
                n = 8 if eup_on else 10
                msg = f"Exit at close if < EMA{n} (₹{_fmt_price(exit_threshold)})"
                log.info("next_action=SELL_TOMORROW close<EMA%s ema=%s", n, _fmt_price(exit_threshold))
                return {
                    "code": "SELL_TOMORROW",
                    "text": msg,
                    "reasons": [f"close<EMA{n}"],
                    "refs": {"stop_now": stop_now, "ema_n": n, "ema_value": exit_threshold}
                }
        except Exception as e:
            log.exception("SELL_TOMORROW check failed: %s", e)

    # ---------- 3) In-trade holds ----------
    if in_pos:
        if eup_on:
            log.info("next_action=HOLD_TIGHT reason=euphoria_on")
            return {
                "code": "HOLD_TIGHT",
                "text": "Hold (trend strong)",
                "reasons": ["euphoria_on"],
                "refs": {"stop_now": stop_now, "ema_n": 8, "ema_value": exit_threshold}
            }
        if _breakeven_active(position, price):
            msg = "Hold (breakeven active)"
            log.info("next_action=HOLD_BREAKEVEN")
            return {
                "code": "HOLD_BREAKEVEN",
                "text": msg,
                "reasons": ["breakeven_active"],
                "refs": {"stop_now": stop_now, "entry_price_locked": entry_locked}
            }
        # default in-trade hold
        if stop_now is not None:
            msg = f"Hold (trail stop at ₹{_fmt_price(stop_now)})"
        else:
            msg = f"Hold (above EMA{8 if eup_on else 10})"
        log.info("next_action=HOLD")
        return {
            "code": "HOLD",
            "text": msg,
            "reasons": ["in_position"],
            "refs": {"stop_now": stop_now, "ema_n": 8 if eup_on else 10, "ema_value": exit_threshold}
        }

    # ---------- 4) Not in trade: entry logic ----------
    # 4a) Clean breakout
    pivot = indicators.get("pivot_20d")
    relvol20 = indicators.get("relvol20")
    if _gateway_breakout(indicators):
        try:
            if pivot is not None and price is not None and float(price) >= float(pivot):
                extended = _extended_over_pivot(indicators)
                if not extended:
                    msg = f"Buy on breakout (≥ ₹{_fmt_price(pivot)})"
                    log.info("next_action=BUY_BREAKOUT pivot=%s", _fmt_price(pivot))
                    return {
                        "code": "BUY_BREAKOUT",
                        "text": msg,
                        "reasons": ["gateway_passed", "pivot_cleared"],
                        "refs": {
                            "level": pivot,
                            "relvol20": relvol20,
                            "ema_n": 10,
                            "ema_value": indicators.get("ema10") or indicators.get("ema_slow_value")
                        }
                    }
        except Exception as e:
            log.exception("BUY_BREAKOUT check failed: %s", e)

    # 4b) Pullback entry after extension or hot RSI
    rsi14 = indicators.get("rsi14")
    extended = _extended_over_pivot(indicators)
    try:
        rsi_hot = rsi14 is not None and float(rsi14) > 75.0
    except Exception:
        rsi_hot = False
    if extended or rsi_hot:
        a, b = _pullback_zone(indicators)
        if a is not None and b is not None:
            msg = f"Buy on pullback (₹{_fmt_price(a)}–₹{_fmt_price(b)})"
        else:
            msg = "Buy on pullback (near EMA10)"
        # Guard: do NOT suggest pullback if price is still below the breakout pivot.
        try:
            below_pivot = pivot is not None and price is not None and float(price) < float(pivot)
        except Exception:
            below_pivot = False
        if not below_pivot:
            log.info("next_action=BUY_PULLBACK zone_low=%s zone_high=%s", _fmt_price(a), _fmt_price(b))
            return {
                "code": "BUY_PULLBACK",
                "text": msg,
                "reasons": ["extended" if extended else "rsi_hot"],
                "refs": {"entry_low": a, "entry_high": b, "ema_n": 10, "ema_value": indicators.get("ema10")}
            }
        # else: fall through; soft gates after entry attempts will cleanly return WATCH

    # 4c) Starter position (early)
    adx14 = indicators.get("adx14")
    try:
        early = (adx14 is not None and float(adx14) >= 20.0) and (relvol20 is not None and float(relvol20) >= 2.0)
    except Exception:
        early = False
    if early:
        log.info("next_action=BUY_STARTER")
        return {
            "code": "BUY_STARTER",
            "text": "Starter position (small size)",
            "reasons": ["early_strength"],
            "refs": {"ema_n": 10, "ema_value": indicators.get("ema10")}
        }
    # ---------- 4.9) Soft gates AFTER entry attempts ----------
    if not in_pos:
        failed = _gates_failed(indicators)
        if failed:
            msg = "Watch — weak momentum/volume/structure"
            log.info("next_action=WATCH gates_failed=%s", failed)
            return {
                "code": "WATCH",
                "text": msg,
                "reasons": failed,
                "refs": {"failed_gates": failed, "ema_n": 8 if eup_on else 10, "ema_value": exit_threshold}
            }

    # ---------- 5) Default: WATCH ----------
    log.info("next_action=WATCH default")
    return {
        "code": "WATCH",
        "text": "Watch — Not actionable yet",
        "reasons": ["setup_incomplete"],
        "refs": {"stop_now": stop_now, "ema_n": ema_n, "ema_value": ema_val}
    }

def method_pill_for(indicators: Dict[str, Any], _score_row: Dict[str, Any]) -> str:
    # Prefer EMA8 when euphoria is on; else the configured slow EMA (fallback 10)
    rsi = indicators.get("rsi14")
    adx = indicators.get("adx14")
    adx_slope_5 = indicators.get("adx_slope_5") or 0
    eup = False
    try:
        rsi_f = float(rsi) if rsi is not None else None
        adx_f = float(adx) if adx is not None else None
        eup = (rsi_f is not None and adx_f is not None) and (
            (rsi_f >= 75 and adx_f >= 30) or (rsi_f >= 70 and adx_f >= 25 and adx_slope_5 > 0)
        )
    except Exception:
        eup = False

    if eup:
        return "EMA8"
    return f"EMA{indicators.get('ema_slow') or 10}"

