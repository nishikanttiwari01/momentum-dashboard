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
        badges.append({"code":"NEW_HIGH","text":"📈 New 52W High"})
    if (pivot_clear_pct or -1) >= 1.0: bq += 1
    if (base_len_bars or 0) >= 10: bq += 1
    score += bq

    # Volume/OBV → up to 3
    vol = 0
    if (relvol20 or 0) >= 1.5: vol += 1
    if (vol_z or 0) >= 2.0: vol += 1
    if obv_above_ma: vol += 1
    score += vol

    score_pct = round((score/12.0)*100.0, 2)
    # Momentum badges
    if score >= 8:
        badges.append({"code":"HIGH_MOMENTUM","text":"🔥 High Momentum"})
    if score >= 10 and (rsi or 0) >= 60 and (adx or 0) >= 30 and (pivot_clear_pct or 0) >= 2.0:
        badges.append({"code":"VERY_HIGH_BREAKOUT","text":"💥 Very High Breakout"})
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
               sector_rank_1to10: Optional[int]) -> Tuple[int, List[Dict[str,str]]]:

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
            prox = 0 if gap >= 5 else round(10 * (1 - gap/5.0))
    pivot_s = 0
    if pivot_clear_pct is not None and pivot_clear_pct > 0:
        pivot_s = min(10, 5 + 2.5 * min(pivot_clear_pct, 2))
    base_s = 0
    if base_len_bars is not None:
        base_s = _clamp((base_len_bars-10)/(40-10), 0, 1)*6
    base_s += min(4, squeeze_flags)  # squeeze/NR7 etc
    base_s = min(10, round(base_s))
    P2 = int(round(prox + pivot_s + base_s))

    # P3: Accumulation & Volume (0–25)
    relvol_s = 0
    if relvol20 is not None:
        if relvol20 < 1.0: relvol_s = 0
        elif relvol20 < 1.5: relvol_s = round((relvol20-1.0)/0.5 * 6)
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

    # Bonuses / penalties
    if (adx_slope_5 or 0) >= 5: score += 2
    if (rsi or 0) > 80 or ((adx or 0) > 45 and (adx_slope_5 or 0) > 0):
        score -= 5
    if pivot_clear_pct is not None:
        ext = max(0.0, pivot_clear_pct - 5.0)
        score -= min(10, round(ext * 1.5))

    score = int(_clamp(score, 0, 100))
    badges: List[Dict[str,str]] = []
    if 75 <= score < 85:
        badges.append({"code":"HIGH_MOMENTUM","text":"🔥 High Momentum"})
    if score >= 85 and (rsi or 0) >= 60 and (adx or 0) >= 30 and (pivot_clear_pct or 0) >= 2.0:
        badges.append({"code":"VERY_HIGH_BREAKOUT","text":"💥 Very High Breakout"})
    return score, badges

def recommendation_and_reason(score_0_100: int, rsi: float|None, adx: float|None,
                              prox_52w: float|None, relvol20: float|None, pivot_clear_pct: float|None) -> tuple[str,str]:
    yes = score_0_100 >= 60
    rec = "Yes" if yes else "No"
    reason = (f"{rec} — {score_0_100}/100. "
              f"RSI {round(rsi,1) if rsi is not None else '—'}, ADX {round(adx,1) if adx is not None else '—'}; "
              f"{'new 52W high' if (prox_52w or -1) >= 0 else f'{round(prox_52w,2)}% vs 52W high' if prox_52w is not None else '—'}, "
              f"RelVol {round(relvol20,2) if relvol20 is not None else '—'}, "
              f"pivot clear {round(pivot_clear_pct,2)}%" if pivot_clear_pct is not None else "")
    return rec, reason
