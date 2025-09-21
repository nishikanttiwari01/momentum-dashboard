# backend/app/domain/next_action.py
from __future__ import annotations
from typing import Any, Dict, List, Tuple, Optional

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
    if price_f is not None and price_f >= entry_f * 1.05:
        return True
    return False

def _exit_close_threshold(ind: Dict[str, Any], eup_on: bool) -> Optional[float]:
    """
    Exit at close if Close < EMA{n}, where n = 10 normally, 8 if euphoria.
    We accept either explicit ema values or fall back to the 'ema_slow_value' that your FE used.
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
    - Volatility: ATR14% > 8 (personal style)
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

    # ---------- 0) Hard prefilters (only if NOT already in a trade) ----------
    in_pos = _in_position(position)
    if not in_pos:
        blocked, why = _prefilter_ignore(indicators)
        if blocked:
            return {
                "code": "IGNORE",
                "text": f"Ignore — {why}",
                "reasons": [why],
                "refs": {"stop_now": stop_now, "ema_n": ema_n, "ema_value": ema_val, "exit_close_threshold": exit_threshold}
            }

    # ---------- 1) SELL_NOW (intraday stop touched) ----------
    if price is not None and stop_now is not None:
        try:
            if float(price) <= float(stop_now):
                return {
                    "code": "SELL_NOW",
                    "text": f"Sell now — Stop-loss ₹{_fmt_price(stop_now)} touched",
                    "reasons": ["Price ≤ stop_now"],
                    "refs": {"stop_now": stop_now, "ema_n": ema_n, "ema_value": ema_val, "exit_close_threshold": exit_threshold}
                }
        except Exception:
            pass

    # ---------- 2) SELL_TOMORROW (EOD close < threshold) ----------
    # Only trigger this when the bar is complete. Expect the caller to pass an EOD flag if needed.
    is_eod = _bool(indicators.get("is_eod")) or _bool(indicators.get("market_closed"))
    if is_eod and price is not None and exit_threshold is not None:
        try:
            if float(price) < float(exit_threshold):
                n = 8 if eup_on else 10
                return {
                    "code": "SELL_TOMORROW",
                    "text": f"Sell tomorrow at open — Close < EMA{n} (₹{_fmt_price(exit_threshold)})",
                    "reasons": [f"Close < EMA{n}"],
                    "refs": {"stop_now": stop_now, "ema_n": n, "ema_value": exit_threshold}
                }
        except Exception:
            pass

    # ---------- 3) In-trade holds ----------
    if in_pos:
        if eup_on:
            return {
                "code": "HOLD_TIGHT",
                "text": "Hold — Tight protection active (Euphoria)",
                "reasons": ["Euphoria=On"],
                "refs": {"stop_now": stop_now, "ema_n": 8 if eup_on else 10, "ema_value": exit_threshold}
            }
        if _breakeven_active(position, price):
            return {
                "code": "HOLD_BREAKEVEN",
                "text": f"Hold — Stop moved to breakeven (₹{_fmt_price(entry_locked)})",
                "reasons": ["Breakeven active"],
                "refs": {"stop_now": stop_now, "entry": entry_locked}
            }
        # default in-trade hold
        return {
            "code": "HOLD",
            "text": f"Hold — Trail stop at ₹{_fmt_price(stop_now)}" if stop_now else "Hold — Trail",
            "reasons": ["In position"],
            "refs": {"stop_now": stop_now, "ema_n": 8 if eup_on else 10, "ema_value": exit_threshold}
        }

    # ---------- 4) Not in trade: entry logic ----------
    # 4a) Clean breakout
    pivot = indicators.get("pivot_20d")
    pivot_clear_pct = indicators.get("pivot_clear_pct")
    relvol20 = indicators.get("relvol20")
    adx14 = indicators.get("adx14")
    rsi14 = indicators.get("rsi14")

    if _gateway_breakout(indicators):
        try:
            if pivot is not None and price is not None and float(price) >= float(pivot):
                # limit chasing if > +5% over pivot
                extended = _extended_over_pivot(indicators)
                if not extended:
                    return {
                        "code": "BUY_BREAKOUT",
                        "text": f"Buy now — Breakout above ₹{_fmt_price(pivot)}",
                        "reasons": ["Gateway passed", "Pivot cleared", "Volume/momentum adequate"],
                        "refs": {
                            "entry": price,
                            "pivot": pivot,
                            "stop_now": stop_now,
                            "ema_n": 10,
                            "ema_value": indicators.get("ema10") or indicators.get("ema_slow_value")
                        }
                    }
        except Exception:
            pass

    # 4b) Pullback entry after extension or hot RSI
    extended = _extended_over_pivot(indicators)
    try:
        rsi_hot = rsi14 is not None and float(rsi14) > 75.0
    except Exception:
        rsi_hot = False
    if extended or rsi_hot:
        a, b = _pullback_zone(indicators)
        txt = f"Buy on pullback ₹{_fmt_price(a)}–₹{_fmt_price(b)}" if a and b else "Buy on pullback (near EMA10)"
        return {
            "code": "BUY_PULLBACK",
            "text": txt,
            "reasons": ["Extended" if extended else "RSI hot"],
            "refs": {"A": a, "B": b, "pivot": pivot, "ema_n": 10, "ema_value": indicators.get("ema10")}
        }

    # 4c) Starter position (early)
    try:
        early = (adx14 is not None and float(adx14) >= 20.0) and (relvol20 is not None and float(relvol20) >= 2.0)
    except Exception:
        early = False
    if early:
        return {
            "code": "BUY_STARTER",
            "text": "Starter buy (½ size) — Add if close > pivot",
            "reasons": ["Early strength"],
            "refs": {"pivot": pivot, "ema_n": 10, "ema_value": indicators.get("ema10")}
        }

    # ---------- 5) Default: WATCH ----------
    return {
        "code": "WATCH",
        "text": "Watch — Not actionable yet",
        "reasons": ["Setup incomplete"],
        "refs": {"stop_now": stop_now, "ema_n": ema_n, "ema_value": ema_val}
    }

def method_pill_for(indicators: Dict[str, Any], _score_row: Dict[str, Any]) -> str:
    return f"EMA{indicators.get('ema_slow') or 10}"
