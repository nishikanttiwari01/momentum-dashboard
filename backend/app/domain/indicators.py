# backend/app/domain/indicators.py
from __future__ import annotations

from typing import Optional, Tuple

import numpy as np
import pandas as pd

TD_1M, TD_3M, TD_6M, TD_12M, TD_1W = 21, 63, 126, 252, 5


def _ensure_float(series: pd.Series) -> pd.Series:
    return series.astype(float)


def _wilder_rma(x: pd.Series, n: int) -> pd.Series:
    """Wilder's RMA (used by RSI/ADX)."""
    x = _ensure_float(x)
    return x.ewm(alpha=1.0 / n, adjust=False).mean()


def ema(close: pd.Series, n: int) -> pd.Series:
    return _ensure_float(close).ewm(span=n, adjust=False).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    close_f = _ensure_float(close)
    delta = close_f.diff()
    up = np.where(delta > 0, delta, 0.0)
    dn = np.where(delta < 0, -delta, 0.0)
    rs = _wilder_rma(pd.Series(up, index=close.index), n) / _wilder_rma(pd.Series(dn, index=close.index), n)
    return 100.0 - (100.0 / (1.0 + rs))


def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr


def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    tr = _true_range(high, low, close)
    return _wilder_rma(tr, n)


def adx(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.DataFrame:
    high_f = _ensure_float(high)
    low_f = _ensure_float(low)
    close_f = _ensure_float(close)

    up_move = high_f.diff()
    down_move = -low_f.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr = _true_range(high_f, low_f, close_f)
    atr_n = _wilder_rma(tr, n)

    plus_di = 100.0 * _wilder_rma(pd.Series(plus_dm, index=high.index), n) / atr_n
    minus_di = 100.0 * _wilder_rma(pd.Series(minus_dm, index=high.index), n) / atr_n

    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)) * 100.0
    adx_val = _wilder_rma(dx, n)
    adx_slope_5 = adx_val - adx_val.shift(TD_1W)
    return pd.DataFrame(
        {
            "adx": adx_val,
            "plus_di": plus_di,
            "minus_di": minus_di,
            "adx_slope_5": adx_slope_5,
        }
    )


def relvol(volume: pd.Series, n: int = 20) -> pd.Series:
    volume_f = _ensure_float(volume)
    v_ma = volume_f.rolling(n, min_periods=n).mean()
    out = (volume_f / v_ma).replace([np.inf, -np.inf], np.nan)
    return out


def proximity_52w_high(close: pd.Series, high: pd.Series, win: int = TD_12M) -> pd.Series:
    roll_max = high.rolling(win, min_periods=2).max()
    return 100.0 * (close / roll_max - 1.0)


def returns_block(adj_close: pd.Series) -> pd.DataFrame:
    def pct(n: int) -> pd.Series:
        base = adj_close.shift(n)
        return 100.0 * (adj_close / base - 1.0)

    ret_1m = pct(TD_1M)
    ret_3m = pct(TD_3M)
    ret_6m = pct(TD_6M)
    ret_12_1m = 100.0 * (adj_close.shift(TD_1M) / adj_close.shift(TD_12M) - 1.0)
    ret_1w_val = pct(TD_1W)
    return pd.DataFrame(
        {
            "ret_1w": ret_1w_val,
            "ret_1m": ret_1m,
            "ret_3m": ret_3m,
            "ret_6m": ret_6m,
            "ret_12_1m": ret_12_1m,
        }
    )


# ---------------------------------------------------------------------------
# Extended indicator helpers for Phase-15 momentum spec.
# ---------------------------------------------------------------------------

def _adjusted_ohlcv(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series]:
    """
    Return adjusted OHLCV using adj_close as anchor.
    Volume is divided by the adjustment factor to maintain turnover continuity.
    """
    adj_close = df.get("adj_close")
    close = df.get("close")
    if adj_close is None or close is None:
        factor = pd.Series(1.0, index=df.index, dtype=float)
    else:
        close_f = _ensure_float(close)
        adj_f = _ensure_float(adj_close)
        factor = adj_f / close_f.replace(0.0, np.nan)
        factor = factor.replace([np.inf, -np.inf], np.nan).fillna(method="ffill").fillna(1.0)

    adj = pd.DataFrame(index=df.index)
    for col in ("open", "high", "low", "close"):
        if col in df:
            adj[col] = _ensure_float(df[col]) * factor
        else:
            adj[col] = np.nan
    if "volume" in df:
        # Guard against division by zero when factor is zero (shouldn't happen post fill)
        adj["volume"] = _ensure_float(df["volume"]) / factor.replace(0.0, np.nan)
    else:
        adj["volume"] = np.nan

    adj["adj_close"] = _ensure_float(df.get("adj_close", df.get("close", pd.Series(np.nan, index=df.index))))
    return adj, factor


def _winsorize_upper(series: pd.Series, quantile: float = 0.95, window: int = 252) -> pd.Series:
    """Cap a series at the rolling quantile to control extreme spikes."""
    roll_q = series.rolling(window, min_periods=20).quantile(quantile, interpolation="linear")
    capped = series.where((roll_q.isna()) | (series <= roll_q), roll_q)
    return capped


def _n_consecutive_moves(close: pd.Series) -> Tuple[pd.Series, pd.Series]:
    """Return consecutive up and consecutive down counts."""
    delta = close.diff()
    up = (delta > 0).astype(int)
    down = (delta < 0).astype(int)

    n_up = up.copy()
    n_down = down.copy()
    for arr in (n_up, n_down):
        arr.iloc[:] = 0
    for idx in range(1, len(close)):
        if up.iloc[idx]:
            n_up.iloc[idx] = n_up.iloc[idx - 1] + 1
        else:
            n_up.iloc[idx] = 0
        if down.iloc[idx]:
            n_down.iloc[idx] = n_down.iloc[idx - 1] + 1
        else:
            n_down.iloc[idx] = 0
    return n_up, n_down


def _swing_high_pivot(high: pd.Series, window: int = 20, gap: int = 2) -> Tuple[pd.Series, pd.Series]:
    """
    Swing-high pivot with lookback_gap to avoid repaint.
    Returns (pivot_value, pivot_index) where index is expressed as running bar number.
    """
    shifted = high.shift(gap)
    roll = shifted.rolling(window, min_periods=max(gap + 1, 5))
    pivot_val = roll.max()

    def _argmax_or_nan(values: np.ndarray) -> float:
        if np.all(np.isnan(values)):
            return np.nan
        return float(np.nanargmax(values))

    offsets = roll.apply(_argmax_or_nan, raw=True)
    idx = np.arange(len(high))
    pivot_index = idx - gap - (window - 1 - offsets)
    pivot_index = pd.Series(pivot_index, index=high.index, dtype=float)
    pivot_index = pivot_index.where(~pivot_index.isna(), np.nan)
    return pivot_val, pivot_index


def _recent_failed_breakout(pivot_clear_pct: pd.Series, lookback: int = 10) -> pd.Series:
    """
    Identify whether there was a breakout attempt within the lookback window
    that subsequently failed (price back below pivot today).
    """
    breakout = pivot_clear_pct > 1.0
    rolling_any = breakout.rolling(lookback, min_periods=1).max()
    failed = rolling_any.astype(bool) & (pivot_clear_pct <= 0)
    return failed.astype(bool)


def _obv_block(adj_close: pd.Series, adj_volume: pd.Series, adj_factor: pd.Series) -> pd.DataFrame:
    """Compute OBV metrics with corporate-action freeze."""
    price_delta = adj_close.diff()
    direction = np.sign(price_delta.fillna(0.0))

    # corporate action detected when adjustment factor jumps materially
    factor_ratio = adj_factor / adj_factor.shift(1)
    corp_event = factor_ratio.abs().gt(1.05).fillna(False)

    increments = direction * adj_volume.fillna(0.0)
    increments = increments.where(~corp_event, 0.0)
    obv = increments.cumsum()
    obv = obv.where(~corp_event, obv.shift(1))
    obv_ma30 = obv.rolling(30, min_periods=15).mean()
    obv_slope_10 = obv - obv.shift(10)
    obv_above_ma = obv > obv_ma30

    return pd.DataFrame(
        {
            "obv": obv,
            "obv_ma30": obv_ma30,
            "obv_slope_10": obv_slope_10,
            "obv_above_ma": obv_above_ma.astype(float),
        }
    )


def compute_indicator_frame(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute the full indicator set required for scoring/alerts.
    Expects df with columns open, high, low, close, adj_close, volume (additional columns optional).
    """
    adj, factor = _adjusted_ohlcv(df)
    close = adj["close"]
    high = adj["high"]
    low = adj["low"]
    volume = adj["volume"]
    adj_close = adj["adj_close"]

    ind = pd.DataFrame(index=df.index)
    ind["ema10"] = ema(close, 10)
    ind["ema50"] = ema(close, 50)
    ind["ema200"] = ema(close, 200)
    ind["rsi14"] = rsi(close, 14)

    adx_df = adx(high, low, close, 14)
    ind["adx14"] = adx_df["adx"]
    ind["plus_di"] = adx_df["plus_di"]
    ind["minus_di"] = adx_df["minus_di"]
    ind["adx_slope_5"] = adx_df["adx_slope_5"]
    ind["adx_slope_pos"] = (ind["adx_slope_5"] > 0).astype(float)

    atr14 = atr(high, low, close, 14)
    atr10 = atr(high, low, close, 10)
    ind["atr14_pct"] = (atr14 / close) * 100.0
    ind["atr10_pct"] = (atr10 / close) * 100.0

    raw_relvol = relvol(volume, 20)
    ind["relvol20_raw"] = raw_relvol
    ind["relvol20"] = _winsorize_upper(raw_relvol, quantile=0.95, window=252)

    ind["vol_z20"] = (volume - volume.rolling(20, min_periods=20).mean()) / volume.rolling(20, min_periods=20).std(ddof=0)
    ind["vol_z20"] = ind["vol_z20"].replace([np.inf, -np.inf], np.nan)

    prox = proximity_52w_high(close, high, 252)
    ind["proximity_52w_high_pct"] = prox
    ind["high_252"] = high.rolling(252, min_periods=10).max()

    pivot_val, pivot_idx = _swing_high_pivot(high, window=20, gap=2)
    ind["pivot_high_20"] = pivot_val
    ind["pivot_clear_pct"] = (close / pivot_val - 1.0) * 100.0
    # Base length: bars since pivot index (clip >=0)
    bar_index = pd.Series(np.arange(len(df)), index=df.index, dtype=float)
    ind["base_len_bars"] = (bar_index - pivot_idx).clip(lower=0.0)

    ind["gap_up_pct"] = (adj["open"] / close.shift(1) - 1.0) * 100.0
    rng = high - low
    ind["close_pos_in_bar"] = np.where(rng > 0, (close - low) / rng, np.nan)

    n_up, n_down = _n_consecutive_moves(close)
    ind["n_consecutive_up"] = n_up
    ind["n_consecutive_down"] = n_down

    rets = returns_block(adj_close)
    ind = ind.join(rets, how="left")
    ind["ret_5d"] = rets["ret_1w"]

    traded_value = close * volume
    ind["median_traded_value_20d"] = traded_value.rolling(20, min_periods=5).median()

    obv_block = _obv_block(adj_close, volume, factor)
    ind = ind.join(obv_block, how="left")

    ratio_series = None
    if "delivery_ratio" in df:
        ratio_series = _ensure_float(df["delivery_ratio"])
    elif "deliverable_volume" in df and "volume" in df:
        denom = _ensure_float(df["volume"]).replace(0.0, np.nan)
        ratio_series = (_ensure_float(df["deliverable_volume"]) / denom).clip(lower=0.0, upper=1.5)
    if ratio_series is not None:
        ind["delivery_ratio_20d"] = ratio_series.rolling(20, min_periods=5).mean()
    else:
        ind["delivery_ratio_20d"] = np.nan

    # Recent failed breakout detection
    ind["recent_failed_breakout_10d"] = _recent_failed_breakout(ind["pivot_clear_pct"], lookback=10).astype(float)

    # Daily change convenience fields
    prev_close = close.shift(1)
    ind["pct_today"] = (close - prev_close) * 100.0 / prev_close.replace(0.0, np.nan)
    ind["wk_change"] = close - close.shift(TD_1W)
    ind["wk_change_pct"] = (close / close.shift(TD_1W) - 1.0) * 100.0

    # Mansfield RS placeholder (requires benchmark series; expect caller to overwrite when available)
    ind["mansfield_rs_52"] = np.nan

    # Breadth/Regime placeholders (populated upstream)
    ind["breadth_pct_50dma"] = np.nan
    ind["nifty_regime"] = np.nan
    ind["asm_gsm_flags"] = np.nan
    ind["upper_circuit_hits_60d"] = np.nan

    return ind
