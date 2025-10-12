from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import math
import logging

try:
    from app.core.config import load as load_settings
except Exception:  # pragma: no cover
    load_settings = None  # type: ignore

log = logging.getLogger("app.domain.rules.next_action")

_EUPH_DEFAULTS = {
    "rsi_min": 75.0,
    "adx_min": 30.0,
    "alt_rsi_min": 70.0,
    "alt_adx_min": 25.0,
    "adx_slope5_min": 0.0,
}


def euphoria_thresholds() -> Dict[str, float]:
    """
    Preserve backward-compatible access to momentum euphoria bands until the
    drawer UI switches to the new spec. Falls back to static defaults when
    settings are unavailable (e.g., during tests).
    """
    if load_settings is None:
        return dict(_EUPH_DEFAULTS)
    try:
        cfg = load_settings()
    except Exception:
        log.debug("euphoria_thresholds: config load failed", exc_info=True)
        return dict(_EUPH_DEFAULTS)
    try:
        eup = cfg.rules.euphoria  # type: ignore[attr-defined]
        return {
            "rsi_min": float(getattr(eup, "rsi_min", _EUPH_DEFAULTS["rsi_min"])),
            "adx_min": float(getattr(eup, "adx_min", _EUPH_DEFAULTS["adx_min"])),
            "alt_rsi_min": float(getattr(eup, "alt_rsi_min", _EUPH_DEFAULTS["alt_rsi_min"])),
            "alt_adx_min": float(getattr(eup, "alt_adx_min", _EUPH_DEFAULTS["alt_adx_min"])),
            "adx_slope5_min": float(getattr(eup, "adx_slope5_min", _EUPH_DEFAULTS["adx_slope5_min"])),
        }
    except Exception:
        log.debug("euphoria_thresholds: config missing rules.euphoria", exc_info=True)
        return dict(_EUPH_DEFAULTS)


def _f(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _fmt_price(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"₹{value:,.2f}"


def global_pre_gates(state: Dict[str, Any]) -> bool:
    """
    Hard prerequisites for any buy-type action.
    """
    median_tv = _f(state.get("median_traded_value_20d"))
    atr14_pct = _f(state.get("atr14_pct"))
    close = _f(state.get("close") or state.get("last") or state.get("price"))
    ema50 = _f(state.get("ema50"))

    if median_tv is None or median_tv < 1e8:
        return False
    if atr14_pct is None or atr14_pct > 8.0:
        return False
    if close is None or close < 50.0:
        return False
    if ema50 is None or close < ema50:
        return False
    return True


def min_prox_for_breakout(
    base_len_bars: Optional[float],
    obv_above_ma: Optional[bool],
    obv_slope_pos: Optional[bool],
    adx_slope_pos: Optional[bool],
    recent_failed_breakout_10d: Optional[bool],
) -> float:
    adj = 0.0
    if base_len_bars is not None and base_len_bars >= 20:
        adj -= 1.0
    if obv_above_ma and obv_slope_pos:
        adj -= 1.0
    if adx_slope_pos:
        adj -= 0.5
    if recent_failed_breakout_10d:
        adj += 1.0
    raw = -10.0 + adj
    return max(-12.0, min(-8.0, raw))


def _pullback_signature(close: Optional[float], ema10: Optional[float], atr14_pct: Optional[float],
                        n_down: Optional[float]) -> bool:
    if close is None or ema10 is None:
        return False
    if n_down is not None and n_down >= 2:
        return True
    if atr14_pct is None:
        return False
    atr_mult = atr14_pct / 100.0 * (close or 0)
    if atr_mult is None:
        return False
    diff = abs(close - ema10)
    return diff <= max(atr_mult * 1.5, 0.0)


def _vwap_check(price: Optional[float], intraday_vwap: Optional[float]) -> Tuple[bool, str]:
    if intraday_vwap is None or price is None:
        return True, "VWAP:n/a"
    passes = price >= intraday_vwap
    return passes, f"VWAP:{'pass' if passes else 'fail'}"


def _reason_codes_common(ind: Dict[str, Any]) -> List[str]:
    codes: List[str] = []
    prox = _f(ind.get("proximity_52w_high_pct"))
    if prox is not None:
        codes.append(f"prox52:{prox:.1f}%")
    relvol = _f(ind.get("relvol20"))
    if relvol is not None:
        codes.append(f"RelVol:{relvol:.1f}x")
    adx = _f(ind.get("adx14"))
    adx_slope_pos = bool(ind.get("adx_slope_pos"))
    if adx is not None:
        codes.append(f"ADX:{adx:.0f}{'↑' if adx_slope_pos else ''}")
    n_up = _f(ind.get("n_consecutive_up"))
    if n_up is not None:
        codes.append(f"run_up:{int(n_up)}")
    return codes


def _build_result(code: str, text: str, reasons: List[str], refs: Dict[str, Any], reason_codes: List[str]) -> Dict[str, Any]:
    return {
        "code": code,
        "text": text,
        "reasons": reasons,
        "refs": refs,
        "reason_codes": reason_codes,
    }


def compute_next_action(*, price: Optional[float], indicators: Dict[str, Any], position: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluate next action per 2025-10-12A spec.
    Returns dict(code=NONE/BUY_BREAKOUT/BUY_PULLBACK/BUY_STARTER, reasons, refs, reason_codes).
    """
    price_now = _f(price) or _f(indicators.get("close") or indicators.get("last"))
    ind = dict(indicators)
    ind.setdefault("close", price_now)
    regime = str(ind.get("nifty_regime") or "").upper()

    if position and position.get("entry_price_locked"):
        return _build_result(
            "NONE",
            "Already in position",
            ["in_position"],
            {"entry_price": position.get("entry_price_locked")},
            ["in_position"],
        )

    if not global_pre_gates(ind):
        reasons = ["pre_gates_fail"]
        reason_codes = ["gates:fail"]
        return _build_result("NONE", "Watch (fails liquidity/volatility gates)", reasons, {}, reason_codes)

    # Common metrics
    prox = _f(ind.get("proximity_52w_high_pct"))
    pivot_clear = _f(ind.get("pivot_clear_pct"))
    relvol20 = _f(ind.get("relvol20"))
    adx14 = _f(ind.get("adx14"))
    adx_slope_pos = bool(ind.get("adx_slope_pos"))
    obv_above = bool(ind.get("obv_above_ma"))
    obv_slope_pos = _f(ind.get("obv_slope_10"))
    if obv_slope_pos is not None:
        obv_slope_pos = obv_slope_pos > 0
    n_up = _f(ind.get("n_consecutive_up"))
    base_len = _f(ind.get("base_len_bars"))
    recent_fail = bool(ind.get("recent_failed_breakout_10d"))
    intraday_vwap = _f(ind.get("intraday_vwap"))
    live_flag = bool(ind.get("live_intraday"))

    # --- Breakout evaluation ---
    if prox is not None and pivot_clear is not None and relvol20 is not None and adx14 is not None:
        min_prox = min_prox_for_breakout(
            base_len_bars=base_len,
            obv_above_ma=obv_above,
            obv_slope_pos=obv_slope_pos,
            adx_slope_pos=adx_slope_pos,
            recent_failed_breakout_10d=recent_fail,
        )
        prox_ok = prox >= min_prox
        pivot_ok = 0.0 <= pivot_clear <= 5.0
        relvol_ok = relvol20 >= 1.5
        adx_ok = adx14 >= 25.0 and adx_slope_pos
        obv_ok = obv_above
        stretch_ok = (n_up or 0) <= 2
        vwap_ok, vwap_code = _vwap_check(price_now, intraday_vwap if live_flag else None)
        gap = _f(ind.get("gap_up_pct"))
        close_pos = _f(ind.get("close_pos_in_bar"))
        gap_suppress = bool(gap is not None and gap > 4.0 and close_pos is not None and close_pos < 0.5)

        if prox_ok and pivot_ok and relvol_ok and adx_ok and obv_ok and stretch_ok and vwap_ok and not gap_suppress:
            codes = _reason_codes_common(ind)
            codes.extend([
                f"prox_gate:{prox:.1f}>={min_prox:.1f}",
                f"pivot:{pivot_clear:.1f}%",
                f"RelVol:{relvol20:.1f}x",
                f"{vwap_code}",
            ])
            text = f"Buy breakout near {_fmt_price(ind.get('pivot_high_20'))}"
            refs = {
                "min_prox": min_prox,
                "pivot_clear_pct": pivot_clear,
                "relvol20": relvol20,
                "adx14": adx14,
                "n_consecutive_up": n_up,
                "intraday_vwap": intraday_vwap,
            }
            reasons = ["clean_breakout"]
            return _build_result("BUY_BREAKOUT", text, reasons, refs, codes)

    # --- Pullback evaluation ---
    ema50 = _f(ind.get("ema50"))
    ema200 = _f(ind.get("ema200"))
    ema10 = _f(ind.get("ema10"))
    close_above_ema50 = price_now is not None and ema50 is not None and price_now >= ema50
    trend_ok = close_above_ema50
    prefer_trend = ema50 is not None and ema200 is not None and ema50 >= ema200
    n_down = _f(ind.get("n_consecutive_down"))
    atr14_pct = _f(ind.get("atr14_pct"))
    pullback_sig = _pullback_signature(price_now, ema10, atr14_pct, n_down)
    reversal_ok = (_f(ind.get("close_pos_in_bar")) or 0) >= 0.6
    relvol_pullback = _f(ind.get("relvol20"))
    relvol_pull_ok = relvol_pullback is not None and relvol_pullback >= 1.2
    obv_slope_ok = _f(ind.get("obv_slope_10"))
    obv_slope_ok = obv_slope_ok is not None and obv_slope_ok > 0
    rsi14 = _f(ind.get("rsi14"))
    rsi_block = rsi14 is not None and rsi14 < 35.0

    if trend_ok and pullback_sig and reversal_ok and relvol_pull_ok and obv_slope_ok and not rsi_block:
        codes = _reason_codes_common(ind)
        codes.append(f"pullback:ema10")
        if prefer_trend:
            codes.append("trend:aligned")
        text = f"Buy pullback near {_fmt_price(ema10)}"
        refs = {
            "ema10": ema10,
            "ema50": ema50,
            "ema200": ema200,
            "relvol20": relvol_pullback,
            "n_consecutive_down": n_down,
        }
        reasons = ["first_pullback"]
        return _build_result("BUY_PULLBACK", text, reasons, refs, codes)

    # --- Starter evaluation ---
    relvol_starter = _f(ind.get("relvol20"))
    mansfield = _f(ind.get("mansfield_rs_52"))
    prox_ok_starter = prox is not None and prox >= -15.0
    adx_ok_starter = adx14 is not None and adx14 >= 20.0
    relvol_ok_starter = relvol_starter is not None and relvol_starter >= 1.8
    obv_slope_ok_starter = _f(ind.get("obv_slope_10"))
    obv_slope_ok_starter = obv_slope_ok_starter is not None and obv_slope_ok_starter > 0

    starter_allowed = regime != "DOWN"

    if starter_allowed and prox_ok_starter and adx_ok_starter and relvol_ok_starter and obv_slope_ok_starter:
        codes = _reason_codes_common(ind)
        if mansfield is not None:
            codes.append(f"RS:{mansfield:.2f}")
        codes.append("starter:early_strength")
        text = "Starter buy (early strength, smaller size)"
        refs = {
            "prox_52w": prox,
            "adx14": adx14,
            "relvol20": relvol_starter,
        }
        reasons = ["early_strength"]
        return _build_result("BUY_STARTER", text, reasons, refs, codes)

    if not starter_allowed and prox_ok_starter and adx_ok_starter and relvol_ok_starter and obv_slope_ok_starter:
        codes = _reason_codes_common(ind)
        codes.append("starter_blocked:regime")
        return _build_result("NONE", "Starter blocked in current regime", ["starter_blocked"], {}, codes)

    return _build_result("NONE", "No actionable setup", ["no_match"], {}, _reason_codes_common(ind))


__all__ = [
    "euphoria_thresholds",
    "global_pre_gates",
    "min_prox_for_breakout",
    "compute_next_action",
]
