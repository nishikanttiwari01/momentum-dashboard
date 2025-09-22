# backend/app/domain/scoring.py
from __future__ import annotations
from typing import Dict, Any, List, Tuple, Optional
import math

def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

# -------------------------
# Basic (0–12 → %)
# -------------------------
def basic_score(rsi: Optional[float],
                adx: Optional[float],
                adx_slope_5: Optional[float],
                is_new_52w_high: bool,
                pivot_clear_pct: Optional[float],
                base_len_bars: Optional[int],
                relvol20: Optional[float],
                vol_z: Optional[float],
                obv_above_ma: Optional[bool]) -> Tuple[int, float, List[Dict[str, str]]]:
    score = 0
    badges: List[Dict[str, str]] = []

    # RSI bands → 0..3
    if rsi is not None:
        if 50 <= rsi < 55: score += 1
        elif 55 <= rsi < 65: score += 2
        elif 65 <= rsi < 72: score += 3
        elif 72 <= rsi < 80: score += 2
        elif rsi >= 80: score += 1

    # ADX bands + slope bonus → 0..3
    adx_band = 0
    if adx is not None:
        if 20 <= adx < 25: adx_band = 1
        elif 25 <= adx < 35: adx_band = 2
        elif 35 <= adx < 45: adx_band = 3
        else: adx_band = 0
    slope_bonus = 1 if (adx_slope_5 or 0) > 0 else 0
    score += min(3, adx_band + slope_bonus)

    # Breakout quality → up to 3
    bq = 0
    if is_new_52w_high:
        bq += 1
        # NEW SHAPE
        badges.append({"category": "BREAKOUT", "label": "📈 New 52W High"})
    if (pivot_clear_pct or -1) >= 1.0: bq += 1
    if (base_len_bars or 0) >= 10: bq += 1
    score += bq

    # Volume/OBV → up to 3
    vol = 0
    if (relvol20 or 0) >= 1.5: vol += 1
    if (vol_z or 0) >= 2.0: vol += 1
    if obv_above_ma: vol += 1
    score += vol

    score_pct = round((score / 12.0) * 100.0, 2)

    # ---- Unified MOMENTUM badge (always present, based on % bracket)
    IGNORE_PCT   = 45   # very low -> IGNORE
    WATCH_PCT    = 60   # low -> WATCH
    HIGH_PCT     = 75   # high -> MOMENTUM
    BREAKOUT_PCT = 85   # strong + RSI/ADX/pivot -> BREAKOUT

    if score_pct < IGNORE_PCT:
        badges.append({"category": "IGNORE", "label": "IGNORE"})
    elif score_pct < WATCH_PCT:
        badges.append({"category": "WATCH", "label": "LOW MOMENTUM"})
    elif score_pct >= BREAKOUT_PCT and (rsi or 0) >= 60 and (adx or 0) >= 30 and (pivot_clear_pct or 0) >= 2.0:
        badges.append({"category": "BREAKOUT", "label": "VERY HIGH BREAKOUT"})
    elif score_pct < HIGH_PCT:
        badges.append({"category": "MOMENTUM", "label": "MEDIUM MOMENTUM"})
    else:
        badges.append({"category": "MOMENTUM", "label": "HIGH MOMENTUM"})

    return score, score_pct, badges

# -------------------------
# Full (0–100)
# -------------------------
def full_score(rsi: Optional[float],
               adx: Optional[float],
               adx_slope_5: Optional[float],
               plus_di: Optional[float],
               minus_di: Optional[float],
               proximity_52w_high_pct: Optional[float],
               pivot_clear_pct: Optional[float],
               base_len_bars: Optional[int],
               squeeze_flags: int,
               relvol20: Optional[float],
               vol_z: Optional[float],
               obv_above_ma: Optional[bool],
               obv_slope_pos: Optional[bool],
               delivery_lift: Optional[float],
               regime_points: Optional[int],
               sector_rank_1to10: Optional[int],
               # ---- NEW optional context inputs (kept optional for backward compatibility)
               atr10_pct: Optional[float] = None,
               gap_up_pct: Optional[float] = None,
               close_pos_in_bar: Optional[float] = None
               ) -> Tuple[Optional[int], List[Dict[str,str]]]:

    # ---- NEW: minimal completeness check for Full model
    full_required = [
        rsi, adx, proximity_52w_high_pct, pivot_clear_pct, base_len_bars,
        relvol20, vol_z, obv_above_ma, obv_slope_pos
    ]
    if any(v is None for v in full_required):
        return None, []

    # P1: Momentum (0–35)
    rsi_sub = 0
    if rsi is not None:
        if rsi < 50: rsi_sub = 0
        elif rsi < 55: rsi_sub = 8
        elif rsi < 65: rsi_sub = 14
        elif rsi < 72: rsi_sub = 20
        elif rsi < 80: rsi_sub = 14
        else: rsi_sub = 8
    adx_sub = 0
    if adx is not None:
        if 20 <= adx < 25: adx_sub = 5
        elif 25 <= adx < 35: adx_sub = 10
        elif 35 <= adx < 45: adx_sub = 13
        elif adx >= 45: adx_sub = 15
    if (adx_slope_5 or 0) > 0: adx_sub = min(15, adx_sub + 2)
    if plus_di is not None and minus_di is not None and plus_di <= minus_di:
        adx_sub = int(round(adx_sub * 0.5))
    P1 = min(35, rsi_sub + adx_sub)

    # P2: Breakout Quality (0–30)
    prox = 0
    if proximity_52w_high_pct is not None:
        if proximity_52w_high_pct >= 0.0:  # new high or at high
            prox = 10
        else:
            gap = abs(proximity_52w_high_pct)
            prox = 0 if gap >= 5 else round(10 * (1 - gap / 5.0))
    pivot_s = 0
    if pivot_clear_pct is not None and pivot_clear_pct > 0:
        pivot_s = min(10, 5 + 2.5 * min(pivot_clear_pct, 2))
    base_s = 0
    if base_len_bars is not None:
        base_s = _clamp((base_len_bars - 10) / (40 - 10), 0, 1) * 6
    base_s += min(4, squeeze_flags)  # squeeze/NR7 etc
    base_s = min(10, round(base_s))
    P2 = int(round(prox + pivot_s + base_s))

    # P3: Accumulation & Volume (0–25)
    relvol_s = 0
    if relvol20 is not None:
        if relvol20 < 1.0: relvol_s = 0
        elif relvol20 < 1.5: relvol_s = round((relvol20 - 1.0) / 0.5 * 6)
        elif relvol20 < 2.0: relvol_s = 8
        else: relvol_s = 10
    volz_s = min(5, max(0, ((vol_z or 0) - 1.0) * 2.5))
    obv_s  = 5 if (obv_slope_pos and obv_above_ma) else (3 if obv_slope_pos else 0)
    delivery_s = 0
    if delivery_lift is not None:
        if delivery_lift <= 0: delivery_s = 0
        elif delivery_lift < 10: delivery_s = 3
        else: delivery_s = 5
    P3 = int(round(relvol_s + volz_s + obv_s + delivery_s))

    # P4: Context (0–10)
    regime_s = regime_points or 0  # 0/3/6 mapping done upstream
    sector_s = 0
    if sector_rank_1to10 is not None:
        rank = sector_rank_1to10
        sector_s = max(0, 4 - (rank - 1)) if 1 <= rank <= 4 else 0
    P4 = int(_clamp(regime_s + sector_s, 0, 10))

    score = P1 + P2 + P3 + P4

    # Bonuses / penalties (existing + NEW contextual adjustments)
    if (adx_slope_5 or 0) >= 5: score += 2
    if (rsi or 0) > 80 or ((adx or 0) > 45 and (adx_slope_5 or 0) > 0):
        score -= 5
    if pivot_clear_pct is not None:
        ext = max(0.0, pivot_clear_pct - 5.0)
        score -= min(10, round(ext * 1.5))

    # NEW: volatility & gap-fade risk
    if atr10_pct is not None and atr10_pct > 8.0:
        score -= 5
    if (gap_up_pct or 0) > 6.0 and (close_pos_in_bar is not None and close_pos_in_bar < 0.5):
        score -= 3

    score = int(_clamp(score, 0, 100))

    badges: List[Dict[str, str]] = []

    # ---- Unified MOMENTUM badge (always present)
    # ---- Unified MOMENTUM badge (always present, based on % bracket)
    IGNORE_PCT   = 45   # very low -> IGNORE
    WATCH_PCT    = 60   # low -> WATCH
    HIGH_PCT     = 75   # high -> MOMENTUM
    BREAKOUT_PCT = 85   # strong + RSI/ADX/pivot -> BREAKOUT

    if score < IGNORE_PCT:
        badges.append({"category": "IGNORE", "label": "IGNORE"})
    elif score < WATCH_PCT:
        badges.append({"category": "WATCH", "label": "LOW"})
    elif score >= BREAKOUT_PCT and (rsi or 0) >= 60 and (adx or 0) >= 30 and (pivot_clear_pct or 0) >= 2.0:
        badges.append({"category": "BREAKOUT", "label": "BREAKOUT"})
    elif score < HIGH_PCT:
        badges.append({"category": "MOMENTUM", "label": "MEDIUM"})
    else:
        badges.append({"category": "MOMENTUM", "label": "HIGH"})

    return score, badges


# -------------------------
# Reason builder (concise)
# -------------------------
def _reason_phrases(score_0_100: Optional[int],
                    rsi: float|None,
                    adx: float|None,
                    prox_52w: float|None,
                    relvol20: float|None,
                    pivot_clear_pct: float|None,
                    atr14_pct: float|None = None,
                    atr10_pct: float|None = None,
                    gap_up_pct: float|None = None,
                    close_pos_in_bar: float|None = None) -> List[str]:
    phrases: List[str] = []

    # Negative / cautionary
    if rsi is not None and rsi < 55:
        phrases.append("momentum weak")
    if adx is not None and adx < 20:
        phrases.append("trend weak")
    if prox_52w is not None and prox_52w <= -10:
        phrases.append("far from highs")
    if pivot_clear_pct is not None and pivot_clear_pct <= 0:
        phrases.append("below pivot")
    if relvol20 is not None and relvol20 < 1.0:
        phrases.append("low volume")
    vol_pct = atr14_pct if atr14_pct is not None else atr10_pct
    if vol_pct is not None and vol_pct > 8.0:
        phrases.append("too volatile")
    if gap_up_pct is not None and gap_up_pct > 6.0 and (close_pos_in_bar is not None and close_pos_in_bar < 0.5):
        phrases.append("gap & fade")

    # Positive hints (for Yes cases)
    if rsi is not None and rsi >= 65:
        phrases.append("strong momentum")
    if adx is not None and adx >= 25:
        phrases.append("trend strong")
    if pivot_clear_pct is not None and pivot_clear_pct >= 2.0:
        phrases.append("pivot cleared")
    if relvol20 is not None and relvol20 >= 1.5:
        phrases.append("volume strong")

    # Deduplicate while preserving order
    seen = set()
    out: List[str] = []
    for p in phrases:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def recommendation_and_reason(score_0_100: Optional[int],
                              rsi: float|None,
                              adx: float|None,
                              prox_52w: float|None,
                              relvol20: float|None,
                              pivot_clear_pct: float|None,
                              # optional context for phrasing
                              atr14_pct: float|None = None,
                              atr10_pct: float|None = None,
                              gap_up_pct: float|None = None,
                              close_pos_in_bar: float|None = None,
                              *,
                              include_numbers: bool = False) -> tuple[str,str]:
    """
    Returns a (recommendation, reason) tuple.
    - If score is None (Full unavailable), we return a clear fallback message.
    - Otherwise we produce a concise English reason using phrases rather than a long numeric string.
    - Set include_numbers=True if you want the old numeric detail appended after the phrases.
    """
    if score_0_100 is None:
        rec = "No"
        return rec, "Watch — basic fallback (missing indicators for full score)"

    yes = score_0_100 >= 60
    rec = "Yes" if yes else "No"

    phrases = _reason_phrases(
        score_0_100, rsi, adx, prox_52w, relvol20, pivot_clear_pct,
        atr14_pct=atr14_pct, atr10_pct=atr10_pct,
        gap_up_pct=gap_up_pct, close_pos_in_bar=close_pos_in_bar
    )
    if not phrases:
        # Safety: keep something meaningful
        phrases = ["meets minimum criteria"] if yes else ["setup weak"]

    reason = f"{rec} — {score_0_100}/100. " + ", ".join(phrases)

    if include_numbers:
        # Optional numeric tail for debugging (off by default)
        rsi_txt = (f"RSI {round(rsi,1)}" if rsi is not None else None)
        adx_txt = (f"ADX {round(adx,1)}" if adx is not None else None)
        prox_txt = (("new 52W high" if prox_52w is not None and prox_52w >= 0
                     else f"{round(prox_52w,2)}% vs 52W high") if prox_52w is not None else None)
        relv_txt = (f"RelVol {round(relvol20,2)}" if relvol20 is not None else None)
        pivot_txt = (f"pivot {round(pivot_clear_pct,2)}%" if pivot_clear_pct is not None else None)
        tail_bits: List[str] = [x for x in [rsi_txt, adx_txt, prox_txt, relv_txt, pivot_txt] if x]
        vol_txt = (f"ATR% {round(atr14_pct,2)}" if atr14_pct is not None else (f"ATR10% {round(atr10_pct,2)}" if atr10_pct is not None else None))
        if vol_txt: tail_bits.append(vol_txt)
        if gap_up_pct is not None: tail_bits.append(f"gap {round(gap_up_pct,2)}%")
        if tail_bits:
            reason += " · " + ", ".join(tail_bits)

    return rec, reason
