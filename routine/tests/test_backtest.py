"""Backtest math on synthetic data with known answers."""
from __future__ import annotations

import numpy as np
import pandas as pd

from routine import backtest, config, data_io
from routine.tests.conftest import make_price_panel


def _dates(n: int) -> list:
    return [d.date().isoformat() for d in pd.bdate_range("2025-01-01", periods=n)]


def test_forward_returns_exact():
    dates = _dates(10)
    panel = make_price_panel({"AAA": [100, 100, 100, 100, 100, 110, 100, 100, 100, 100]}, dates)
    close = data_io.close_matrix(panel)
    f5 = backtest.forward_returns(close, 5)
    # day0: close 100 -> day5 close 110 = +10%
    assert abs(f5.loc[dates[0], "AAA"] - 10.0) < 1e-9
    # last 5 days have no forward data
    assert np.isnan(f5.loc[dates[5], "AAA"])


def test_max_forward_return_excludes_today():
    dates = _dates(6)
    # today high close, then lower: max of NEXT window must not include today
    panel = make_price_panel({"AAA": [100, 90, 95, 80, 85, 90]}, dates)
    close = data_io.close_matrix(panel)
    mf = backtest.max_forward_return(close, 3)
    # from day0: next 3 closes are 90,95,80 -> max 95 -> -5%
    assert abs(mf.loc[dates[0], "AAA"] - (-5.0)) < 1e-9


def test_breadth_and_regime():
    cfg = config.BacktestConfig(breadth_min_symbols=1)
    dates = _dates(60)
    up = list(np.linspace(100, 200, 60))     # rising: above its 50DMA at the end
    down = list(np.linspace(200, 100, 60))   # falling: below its 50DMA
    panel = make_price_panel({"UP": up, "DOWN": down}, dates)
    close = data_io.close_matrix(panel)
    b = backtest.breadth_series(close, cfg)
    assert abs(b.iloc[-1] - 50.0) < 1e-9  # one above, one below
    labels = backtest.regime_labels(b, cfg)
    assert labels.iloc[-1] == "NEUTRAL"
    assert labels.iloc[0] == "UNKNOWN"  # 50DMA needs >=30 bars


def test_cooldown_first_trigger_only():
    dates = _dates(30)
    sig = pd.DataFrame(
        {
            "symbol": ["AAA"] * 4 + ["BBB"],
            "as_of": [dates[0], dates[1], dates[2], dates[20], dates[1]],
        }
    )
    mask = backtest.apply_cooldown(sig, cooldown_days=5, calendar=dates)
    # AAA day0 = first; day1, day2 suppressed; day20 = new episode; BBB = first
    assert mask.tolist() == [True, False, False, True, True]


def test_run_backtest_end_to_end_synthetic():
    """A stock engineered to surge after its signal day must produce 100%
    hit rate at the signal bucket while baseline stays low."""
    cfg = config.BacktestConfig(
        liquidity_floor_rupees=0.0,
        breadth_min_symbols=1,
        pbss_thresholds=(12, 16),
        cooldown_days=5,
    )
    n = 60
    dates = _dates(n)
    sig_day = 20
    flat = [100.0] * n
    surger = [100.0] * n
    for i in range(sig_day + 1, n):
        surger[i] = min(100.0 * (1.35 ** min((i - sig_day) / 21.0, 1.0)), 140.0)
    panel = make_price_panel({"SURG": surger, "FLAT1": flat, "FLAT2": flat}, dates)

    # inject strong PBSS features on SURG's signal day (pbss = 4+3+2+1+3+2+1+1+2+2+1 = 22)
    m = (panel["symbol"] == "SURG") & (panel["as_of"] == dates[sig_day])
    panel.loc[m, ["vol_z20", "relvol20", "obv_above_ma", "obv_slope_10", "ret_5d",
                  "score", "adx14", "rsi14", "proximity_52w_high_pct",
                  "pivot_clear_pct", "n_consecutive_up"]] = [
        4.0, 3.0, 1.0, 1.0, 10.0, 75.0, 35.0, 60.0, -1.0, 1.0, 4.0
    ]

    res = backtest.run_backtest(cfg=cfg, panel=panel)

    top = res.bucket_stats[res.bucket_stats["pbss_bucket"] == "20-22"].iloc[0]
    assert top["n"] == 1
    assert top["surge_rate_max_ge25pct"] == 100.0
    assert top["hit_rate_ge10pct"] == 100.0

    # Baseline includes SURG's own rising days, so it's nonzero — but the
    # signal bucket must clearly beat it (that's the definition of edge).
    base_row = res.bucket_stats[res.bucket_stats["pbss_bucket"] == "ALL(baseline)"].iloc[0]
    assert base_row["n"] > 50
    assert base_row["hit_rate_ge10pct"] < top["hit_rate_ge10pct"]

    rules = res.threshold_stats.set_index("rule")
    assert rules.loc["PBSS>=16", "n"] == 1
    assert rules.loc["PBSS>=16", "hit_rate_ge10pct"] == 100.0


def test_liquidity_filter_drops_microcaps():
    cfg = config.BacktestConfig(liquidity_floor_rupees=1e7, breadth_min_symbols=1)
    dates = _dates(40)
    panel = make_price_panel({"LIQ": [100] * 40, "MICRO": [100] * 40}, dates)
    panel.loc[panel["symbol"] == "MICRO", "median_traded_value_20d"] = 1e5
    res = backtest.run_backtest(cfg=cfg, panel=panel)
    base = res.bucket_stats[res.bucket_stats["pbss_bucket"] == "ALL(baseline)"].iloc[0]
    # only LIQ rows on evaluable dates (40 - 21 = 19 days)
    assert base["n"] == 19
