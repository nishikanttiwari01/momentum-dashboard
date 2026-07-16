"""PBSS / score backtest engine.

Replays historical daily snapshots, recomputes PBSS from stored features,
computes forward returns from the snapshot close panel, and aggregates
hit rates per PBSS bucket, per threshold rule, and per market regime.

Honesty rules baked in:
- liquidity floor (no untradeable microcaps)
- episode cooldown (one accumulation episode != many signals)
- baseline rows so every number can be compared with "all stocks, same period"
- max-favorable-excursion (surge) reported separately from close-to-close,
  because you cannot bank the intraperiod maximum.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from . import config, data_io, pbss

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------

def forward_returns(close: pd.DataFrame, window: int) -> pd.DataFrame:
    """% return from t close to t+window close (trading-day index)."""
    return (close.shift(-window) / close - 1.0) * 100.0


def max_forward_return(close: pd.DataFrame, window: int) -> pd.DataFrame:
    """% max favorable excursion: highest close in (t, t+window] vs t close."""
    # rolling max of the NEXT `window` closes
    fwd_max = close[::-1].rolling(window, min_periods=1).max()[::-1].shift(-1)
    return (fwd_max / close - 1.0) * 100.0


def breadth_series(close: pd.DataFrame, cfg: config.BacktestConfig) -> pd.Series:
    """% of universe above own 50DMA, computed from the close panel itself."""
    ma50 = close.rolling(50, min_periods=30).mean()
    above = (close > ma50)
    valid = ma50.notna() & close.notna()
    counts = valid.sum(axis=1)
    pct = (above & valid).sum(axis=1) / counts.replace(0, np.nan) * 100.0
    pct[counts < cfg.breadth_min_symbols] = np.nan
    return pct


def regime_labels(breadth: pd.Series, cfg: config.BacktestConfig) -> pd.Series:
    def lab(v: float) -> str:
        if pd.isna(v):
            return "UNKNOWN"
        if v >= cfg.breadth_up:
            return "UP"
        if v <= cfg.breadth_down:
            return "DOWN"
        return "NEUTRAL"

    return breadth.apply(lab)


def apply_cooldown(signals: pd.DataFrame, cooldown_days: int, calendar: List[str]) -> pd.Series:
    """Boolean mask: True for the first trigger of each episode.

    A row is an episode start if the same symbol had no trigger within the
    previous `cooldown_days` trading days.
    """
    pos = {d: i for i, d in enumerate(calendar)}
    sig = signals[["symbol", "as_of"]].copy()
    sig["pos"] = sig["as_of"].map(pos)
    sig = sig.sort_values(["symbol", "pos"])
    prev_pos = sig.groupby("symbol")["pos"].shift(1)
    first = (prev_pos.isna()) | ((sig["pos"] - prev_pos) > cooldown_days)
    return first.reindex(signals.index).fillna(True).astype(bool)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

@dataclass
class BacktestResult:
    bucket_stats: pd.DataFrame
    threshold_stats: pd.DataFrame
    regime_stats: pd.DataFrame
    score_band_stats: pd.DataFrame
    n_days: int = 0
    n_rows: int = 0
    date_range: str = ""
    config_used: Optional[config.BacktestConfig] = None
    notes: List[str] = field(default_factory=list)


def _stats_for(group: pd.DataFrame, cfg: config.BacktestConfig) -> Dict[str, float]:
    n = len(group)
    out: Dict[str, float] = {"n": n}
    if n == 0:
        return out
    f21 = group["fwd_21"]
    out["fwd21_mean_pct"] = round(float(f21.mean()), 2)
    out["fwd21_median_pct"] = round(float(f21.median()), 2)
    out["fwd5_mean_pct"] = round(float(group["fwd_5"].mean()), 2)
    out["win_rate_pct"] = round(float((f21 > 0).mean() * 100.0), 1)
    out[f"hit_rate_ge{int(cfg.hit_gain_pct)}pct"] = round(
        float((f21 >= cfg.hit_gain_pct).mean() * 100.0), 1
    )
    out[f"surge_rate_max_ge{int(cfg.surge_gain_pct)}pct"] = round(
        float((group["max_fwd"] >= cfg.surge_gain_pct).mean() * 100.0), 1
    )
    out["worst_decile_pct"] = round(float(f21.quantile(0.10)), 2)
    return out


def run_backtest(
    cfg: Optional[config.BacktestConfig] = None,
    dates: Optional[List[str]] = None,
    panel: Optional[pd.DataFrame] = None,
) -> BacktestResult:
    cfg = cfg or config.DEFAULT_CONFIG

    if panel is None:
        dates = dates or data_io.list_snapshot_dates()
        log.info("loading %d snapshot dates ...", len(dates))
        panel = data_io.load_feature_panel(dates=dates)
    calendar = sorted(panel["as_of"].unique().tolist())

    close = data_io.close_matrix(panel)

    # forward returns keyed by (as_of, symbol)
    fwd: Dict[str, pd.DataFrame] = {}
    for w in cfg.fwd_windows:
        fwd[f"fwd_{w}"] = forward_returns(close, w)
    max_fwd = max_forward_return(close, cfg.surge_window)

    breadth = breadth_series(close, cfg)
    regimes = regime_labels(breadth, cfg)

    df = panel.copy()
    df["pbss"] = pbss.compute_pbss_frame(df)

    def lookup(mat: pd.DataFrame, frame: pd.DataFrame) -> pd.Series:
        stacked = mat.stack(future_stack=True).rename("v")
        keys = pd.MultiIndex.from_arrays([frame["as_of"], frame["symbol"]])
        return pd.Series(stacked.reindex(keys).values, index=frame.index)

    for name, mat in fwd.items():
        df[name] = lookup(mat, df)
    df["max_fwd"] = lookup(max_fwd, df)
    df["regime"] = df["as_of"].map(regimes)

    notes: List[str] = []

    # ---- eligibility: liquidity + evaluable forward window + valid close ----
    liq = pd.to_numeric(df.get("median_traded_value_20d"), errors="coerce")
    liquid = liq >= cfg.liquidity_floor_rupees
    n_illiquid = int((~liquid.fillna(False)).sum())
    max_w = max(max(cfg.fwd_windows), cfg.surge_window)
    evaluable_dates = set(calendar[:-max_w]) if len(calendar) > max_w else set()
    eligible = (
        liquid.fillna(False)
        & df["as_of"].isin(evaluable_dates)
        & df["fwd_21"].notna()
        & pd.to_numeric(df["close"], errors="coerce").gt(0)
    )
    base = df[eligible].copy()
    notes.append(
        f"rows total={len(df):,} eligible={len(base):,} "
        f"(dropped illiquid/no-liquidity-data={n_illiquid:,}, tail dates without {max_w}d forward data, missing closes)"
    )
    if len(base):
        notes.append(
            f"EFFECTIVE sample (after eligibility): {base['as_of'].min()} -> {base['as_of'].max()} "
            f"({base['as_of'].nunique()} signal days) — liquidity data only exists from ~2025-06"
        )

    # ---- bucket stats (all eligible symbol-days) ----
    rows = []
    for lo, hi in cfg.pbss_buckets:
        g = base[(base["pbss"] >= lo) & (base["pbss"] <= hi)]
        rows.append({"pbss_bucket": f"{lo}-{hi}", **_stats_for(g, cfg)})
    rows.append({"pbss_bucket": "ALL(baseline)", **_stats_for(base, cfg)})
    bucket_stats = pd.DataFrame(rows)

    # ---- threshold rules with episode cooldown (what alerts would fire) ----
    rows = []
    for thr in cfg.pbss_thresholds:
        sig = base[base["pbss"] >= thr]
        if len(sig):
            first_mask = apply_cooldown(sig, cfg.cooldown_days, calendar)
            sig = sig[first_mask.values]
        n_days_eval = base["as_of"].nunique() or 1  # effective days, not calendar
        per_year = round(len(sig) / n_days_eval * 250.0, 0)
        rows.append(
            {
                "rule": f"PBSS>={thr}",
                "signals_per_year": per_year,
                **_stats_for(sig, cfg),
            }
        )
    threshold_stats = pd.DataFrame(rows)

    # ---- regime split for the middle threshold ----
    thr = cfg.pbss_thresholds[len(cfg.pbss_thresholds) // 2]
    sig = base[base["pbss"] >= thr]
    if len(sig):
        sig = sig[apply_cooldown(sig, cfg.cooldown_days, calendar).values]
    rows = []
    for reg in ("UP", "NEUTRAL", "DOWN", "UNKNOWN"):
        g = sig[sig["regime"] == reg]
        b = base[base["regime"] == reg]
        row = {"regime": reg, "rule": f"PBSS>={thr}", **_stats_for(g, cfg)}
        bl = _stats_for(b, cfg)
        row["baseline_fwd21_mean_pct"] = bl.get("fwd21_mean_pct")
        rows.append(row)
    regime_stats = pd.DataFrame(rows)

    # ---- stored composite score bands (the app's 0-100 score) ----
    rows = []
    score = pd.to_numeric(base["score"], errors="coerce")
    for lo, hi, label in [
        (0, 40, "0-40 IGNORE"),
        (41, 55, "41-55 WATCH"),
        (56, 69, "56-69 HIGH"),
        (70, 78, "70-78 BREAKOUT"),
        (79, 100, "79+ ELITE"),
    ]:
        g = base[(score >= lo) & (score <= hi)]
        rows.append({"score_band": label, **_stats_for(g, cfg)})
    score_band_stats = pd.DataFrame(rows)

    return BacktestResult(
        bucket_stats=bucket_stats,
        threshold_stats=threshold_stats,
        regime_stats=regime_stats,
        score_band_stats=score_band_stats,
        n_days=len(calendar),
        n_rows=len(df),
        date_range=f"{calendar[0]} -> {calendar[-1]}" if calendar else "",
        config_used=cfg,
        notes=notes,
    )
