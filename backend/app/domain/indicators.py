# backend/app/domain/indicators.py
from __future__ import annotations
import numpy as np
import pandas as pd

TD_1M, TD_3M, TD_6M, TD_12M, TD_1W = 21, 63, 126, 252, 5

def _wilder_rma(x: pd.Series, n: int) -> pd.Series:
    """Wilder's RMA (used by RSI/ADX)."""
    x = x.astype(float)
    ema = x.ewm(alpha=1.0/n, adjust=False).mean()
    return ema

def ema(close: pd.Series, n: int) -> pd.Series:
    return close.astype(float).ewm(span=n, adjust=False).mean()

def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    up = np.where(delta > 0, delta, 0.0)
    dn = np.where(delta < 0, -delta, 0.0)
    rs = _wilder_rma(pd.Series(up, index=close.index), n) / _wilder_rma(pd.Series(dn, index=close.index), n)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi

def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr

def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    tr = _true_range(high, low, close)
    return _wilder_rma(tr, n)

def adx(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.DataFrame:
    # DM
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr = _true_range(high, low, close)
    atr_n = _wilder_rma(tr, n)

    plus_di = 100.0 * _wilder_rma(pd.Series(plus_dm, index=high.index), n) / atr_n
    minus_di = 100.0 * _wilder_rma(pd.Series(minus_dm, index=high.index), n) / atr_n

    dx = ( (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) ) * 100.0
    adx_val = _wilder_rma(dx, n)
    adx_slope_5 = adx_val - adx_val.shift(TD_1W)
    return pd.DataFrame({
        "adx": adx_val,
        "plus_di": plus_di,
        "minus_di": minus_di,
        "adx_slope_5": adx_slope_5
    })

def relvol(volume: pd.Series, n: int = 20) -> pd.Series:
    v_ma = volume.astype(float).rolling(n, min_periods=n).mean()
    return (volume.astype(float) / v_ma).replace([np.inf, -np.inf], np.nan)

def proximity_52w_high(close: pd.Series, high: pd.Series, win: int = TD_12M) -> pd.Series:
    roll_max = high.rolling(win, min_periods=2).max()
    return 100.0 * (close / roll_max - 1.0)

def returns_block(adj_close: pd.Series) -> pd.DataFrame:
    def pct(n: int) -> pd.Series:
        base = adj_close.shift(n)
        return 100.0 * (adj_close / base - 1.0)
    ret_1m  = pct(TD_1M)
    ret_3m  = pct(TD_3M)
    ret_6m  = pct(TD_6M)
    # 12-1M excludes most recent month
    ret_12_1m = 100.0 * (adj_close.shift(TD_1M) / adj_close.shift(TD_12M) - 1.0)
    ret_1w_val = pct(TD_1W)  # convenience
    return pd.DataFrame({
        "ret_1w": ret_1w_val,
        "ret_1m": ret_1m,
        "ret_3m": ret_3m,
        "ret_6m": ret_6m,
        "ret_12_1m": ret_12_1m
    })
