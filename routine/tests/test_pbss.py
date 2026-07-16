"""PBSS correctness: vectorized == scalar reference, and both match the
original app implementation's semantics (weights, boundaries, max=22)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from routine import pbss


def test_max_score_is_22():
    row = {
        "vol_z20": 4.0,        # 4
        "relvol20": 3.0,       # 3
        "obv_above_ma": True,  # 2
        "obv_slope_10": 1.0,   # 1
        "ret_5d": 10.0,        # 3
        "score": 75.0,         # 2
        "adx14": 35.0,         # 1
        "rsi14": 60.0,         # 1
        "proximity_52w_high_pct": -1.0,  # 2
        "pivot_clear_pct": 1.0,          # 2
        "n_consecutive_up": 4,           # 1
    }
    assert pbss.compute_pbss_row(row) == pbss.PBSS_MAX == 22


def test_empty_row_scores_zero():
    assert pbss.compute_pbss_row({}) == 0
    assert pbss.compute_pbss_row({"vol_z20": None, "rsi14": float("nan")}) == 0


def test_boundaries():
    # vol_z exactly at each boundary
    assert pbss.compute_pbss_row({"vol_z20": 1.0}) == 1
    assert pbss.compute_pbss_row({"vol_z20": 1.5}) == 2
    assert pbss.compute_pbss_row({"vol_z20": 2.0}) == 3
    assert pbss.compute_pbss_row({"vol_z20": 3.0}) == 4
    # rsi sweet spot is inclusive [50, 72]
    assert pbss.compute_pbss_row({"rsi14": 50.0}) == 1
    assert pbss.compute_pbss_row({"rsi14": 72.0}) == 1
    assert pbss.compute_pbss_row({"rsi14": 72.0001}) == 0
    # prox52 band edges
    assert pbss.compute_pbss_row({"proximity_52w_high_pct": 2.0}) == 2
    assert pbss.compute_pbss_row({"proximity_52w_high_pct": 2.01}) == 0
    assert pbss.compute_pbss_row({"proximity_52w_high_pct": -8.0}) == 2
    assert pbss.compute_pbss_row({"proximity_52w_high_pct": -8.01}) == 1


def test_ret_1w_fallback():
    assert pbss.compute_pbss_row({"ret_5d": None, "ret_1w": 8.0}) == 3
    # ret_5d present wins even if smaller
    assert pbss.compute_pbss_row({"ret_5d": 1.0, "ret_1w": 8.0}) == 0


def test_vectorized_equals_reference(random_feature_frame):
    df = random_feature_frame
    vec = pbss.compute_pbss_frame(df)
    ref = df.apply(lambda r: pbss.compute_pbss_row(r.to_dict()), axis=1)
    mismatch = (vec != ref)
    assert not mismatch.any(), (
        f"{mismatch.sum()} mismatches; first bad row:\n"
        f"{df[mismatch].head(3)}\nvec={vec[mismatch].head(3).tolist()} ref={ref[mismatch].head(3).tolist()}"
    )


def test_vectorized_handles_missing_columns():
    df = pd.DataFrame({"vol_z20": [3.5, np.nan]})
    out = pbss.compute_pbss_frame(df)
    assert out.tolist() == [4, 0]
