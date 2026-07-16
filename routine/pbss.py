"""Pre-Breakout Surge Score (PBSS).

Two implementations:
- compute_pbss_row: scalar reference, ported line-for-line from
  backend/app/domain/scoring.py::compute_pre_breakout_score (same weights).
- compute_pbss_frame: vectorized pandas version for backtesting ~1M rows.

tests/test_pbss.py proves the two are equivalent on randomized inputs.
Max possible PBSS = 4+3+2+1+3+2+1+1+2+2+1 = 22.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

PBSS_MAX = 22


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


def compute_pbss_row(row: Dict[str, Any]) -> int:
    """Reference scalar implementation (mirrors the app's scoring.py)."""
    pts = 0.0

    vol_z = _f(row.get("vol_z20"))
    if vol_z is not None:
        if vol_z >= 3.0:
            pts += 4.0
        elif vol_z >= 2.0:
            pts += 3.0
        elif vol_z >= 1.5:
            pts += 2.0
        elif vol_z >= 1.0:
            pts += 1.0

    relvol = _f(row.get("relvol20"))
    if relvol is not None:
        if relvol >= 2.5:
            pts += 3.0
        elif relvol >= 1.8:
            pts += 2.0
        elif relvol >= 1.3:
            pts += 1.0

    obv_above = row.get("obv_above_ma")
    if obv_above is not None and not (isinstance(obv_above, float) and math.isnan(obv_above)):
        if bool(obv_above):
            pts += 2.0
    obv_slope = _f(row.get("obv_slope_10"))
    if obv_slope is not None and obv_slope > 0:
        pts += 1.0

    ret_5d = _f(row.get("ret_5d"))
    if ret_5d is None:
        ret_5d = _f(row.get("ret_1w"))
    if ret_5d is not None:
        if ret_5d >= 8.0:
            pts += 3.0
        elif ret_5d >= 5.0:
            pts += 2.0
        elif ret_5d >= 3.0:
            pts += 1.0

    score = _f(row.get("score"))
    if score is not None:
        if score >= 70:
            pts += 2.0
        elif score >= 60:
            pts += 1.0

    adx = _f(row.get("adx14"))
    if adx is not None and adx >= 30:
        pts += 1.0
    rsi = _f(row.get("rsi14"))
    if rsi is not None and 50.0 <= rsi <= 72.0:
        pts += 1.0

    prox = _f(row.get("proximity_52w_high_pct"))
    if prox is not None:
        if -8.0 <= prox <= 2.0:
            pts += 2.0
        elif -15.0 <= prox < -8.0:
            pts += 1.0

    pivot = _f(row.get("pivot_clear_pct"))
    if pivot is not None:
        if -2.0 <= pivot <= 5.0:
            pts += 2.0
        elif -5.0 <= pivot < -2.0:
            pts += 1.0

    n_up = _f(row.get("n_consecutive_up"))
    if n_up is not None and n_up >= 3:
        pts += 1.0

    return int(round(pts))


def _num(s: pd.Series) -> pd.Series:
    out = pd.to_numeric(s, errors="coerce")
    return out.replace([np.inf, -np.inf], np.nan)


def compute_pbss_frame(df: pd.DataFrame) -> pd.Series:
    """Vectorized PBSS over a feature frame. Returns int series aligned to df."""
    n = len(df)
    idx = df.index
    pts = pd.Series(0.0, index=idx)

    def col(name: str) -> pd.Series:
        if name in df.columns:
            return _num(df[name])
        return pd.Series(np.nan, index=idx)

    vol_z = col("vol_z20")
    pts += np.select(
        [vol_z >= 3.0, vol_z >= 2.0, vol_z >= 1.5, vol_z >= 1.0],
        [4.0, 3.0, 2.0, 1.0],
        default=0.0,
    )

    relvol = col("relvol20")
    pts += np.select([relvol >= 2.5, relvol >= 1.8, relvol >= 1.3], [3.0, 2.0, 1.0], 0.0)

    if "obv_above_ma" in df.columns:
        raw = df["obv_above_ma"]
        as_num = pd.to_numeric(raw, errors="coerce")
        truthy = as_num.fillna(0.0) != 0.0
        # handle plain booleans / bool-like objects too
        if raw.dtype == object:
            truthy = truthy | raw.apply(lambda v: v is True)
        pts += truthy.astype(float) * 2.0

    obv_slope = col("obv_slope_10")
    pts += (obv_slope > 0).astype(float) * 1.0

    ret_5d = col("ret_5d")
    if "ret_1w" in df.columns:
        ret_5d = ret_5d.fillna(col("ret_1w"))
    pts += np.select([ret_5d >= 8.0, ret_5d >= 5.0, ret_5d >= 3.0], [3.0, 2.0, 1.0], 0.0)

    score = col("score")
    pts += np.select([score >= 70, score >= 60], [2.0, 1.0], 0.0)

    adx = col("adx14")
    pts += (adx >= 30).astype(float) * 1.0
    rsi = col("rsi14")
    pts += ((rsi >= 50.0) & (rsi <= 72.0)).astype(float) * 1.0

    prox = col("proximity_52w_high_pct")
    pts += np.select(
        [(prox >= -8.0) & (prox <= 2.0), (prox >= -15.0) & (prox < -8.0)], [2.0, 1.0], 0.0
    )

    pivot = col("pivot_clear_pct")
    pts += np.select(
        [(pivot >= -2.0) & (pivot <= 5.0), (pivot >= -5.0) & (pivot < -2.0)], [2.0, 1.0], 0.0
    )

    n_up = col("n_consecutive_up")
    pts += (n_up >= 3).astype(float) * 1.0

    return pts.round().astype(int)
