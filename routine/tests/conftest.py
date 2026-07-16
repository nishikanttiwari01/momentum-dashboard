from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def rng():
    return np.random.default_rng(42)


@pytest.fixture
def random_feature_frame(rng) -> pd.DataFrame:
    """Randomized feature rows covering edge values, NaNs, and infs."""
    n = 2000
    pick = lambda vals: rng.choice(vals, size=n)
    df = pd.DataFrame(
        {
            "vol_z20": pick([np.nan, -1.0, 0.99, 1.0, 1.49, 1.5, 2.0, 2.99, 3.0, 5.7, np.inf]),
            "relvol20": pick([np.nan, 0.5, 1.29, 1.3, 1.79, 1.8, 2.49, 2.5, 4.2]),
            "obv_above_ma": pick([np.nan, 0.0, 1.0, True, False]),
            "obv_slope_10": pick([np.nan, -5.0, 0.0, 0.001, 123.0]),
            "ret_5d": pick([np.nan, -3.0, 2.99, 3.0, 4.99, 5.0, 7.99, 8.0, 15.0]),
            "ret_1w": pick([np.nan, 3.5, 9.0]),
            "score": pick([np.nan, 10.0, 59.9, 60.0, 69.9, 70.0, 88.0]),
            "adx14": pick([np.nan, 10.0, 29.9, 30.0, 45.0]),
            "rsi14": pick([np.nan, 40.0, 49.9, 50.0, 65.0, 72.0, 72.1, 85.0]),
            "proximity_52w_high_pct": pick([np.nan, -30.0, -15.0, -8.01, -8.0, -3.0, 0.0, 2.0, 2.1]),
            "pivot_clear_pct": pick([np.nan, -10.0, -5.0, -2.01, -2.0, 0.0, 5.0, 5.1, 12.0]),
            "n_consecutive_up": pick([np.nan, 0.0, 2.0, 3.0, 6.0]),
        }
    )
    return df


def make_price_panel(prices: dict, dates: list) -> pd.DataFrame:
    """Long panel from {symbol: [closes...]} + date list, with liquidity high enough to pass filters."""
    rows = []
    for sym, series in prices.items():
        for d, c in zip(dates, series):
            rows.append(
                {
                    "as_of": d,
                    "symbol": sym,
                    "close": c,
                    "score": 50.0,
                    "vol_z20": 0.0,
                    "relvol20": 1.0,
                    "obv_above_ma": 0.0,
                    "obv_slope_10": 0.0,
                    "ret_5d": 0.0,
                    "ret_1w": 0.0,
                    "adx14": 20.0,
                    "rsi14": 55.0,
                    "proximity_52w_high_pct": -20.0,
                    "pivot_clear_pct": -10.0,
                    "n_consecutive_up": 0.0,
                    "median_traded_value_20d": 5e7,
                }
            )
    return pd.DataFrame(rows)
