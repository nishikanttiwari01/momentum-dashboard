"""Central configuration for the momentum routine (backtest + daily job).

No secrets here. Anything sensitive (SMTP etc.) must come from environment
variables / .env — never committed defaults.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROUTINE_DIR = Path(__file__).resolve().parent
REPO_ROOT = ROUTINE_DIR.parent


def parquet_root() -> Path:
    """Parquet lake root. Override with PARQUET_ROOT env var."""
    env = os.environ.get("PARQUET_ROOT")
    if env:
        return Path(env)
    return REPO_ROOT / "backend" / "parquet"


def scores_daily_dir() -> Path:
    return parquet_root() / "scores" / "daily"


def reports_dir() -> Path:
    out = ROUTINE_DIR / "reports"
    out.mkdir(parents=True, exist_ok=True)
    return out


# ---------------------------------------------------------------------------
# Backtest parameters
# ---------------------------------------------------------------------------
@dataclass
class BacktestConfig:
    # Forward-return windows in trading days
    fwd_windows: tuple = (5, 21)
    # Window (trading days) for "max favorable excursion" used by surge hit-rate
    surge_window: int = 21
    # A "surge" = max close within surge_window >= this % above signal close
    surge_gain_pct: float = 25.0
    # A "hit" (modest success) = close after 21 TD >= this %
    hit_gain_pct: float = 10.0
    # Ignore symbols below this 20d median traded value (rupees). Filters
    # untradeable microcaps that inflate backtest stats.
    liquidity_floor_rupees: float = 10_000_000.0  # 1 crore
    # Signal cooldown: only count the FIRST trigger per symbol within this
    # many trading days (mirrors alert cooldown; avoids double counting
    # one accumulation episode as many independent signals).
    cooldown_days: int = 5
    # PBSS buckets reported
    pbss_buckets: tuple = ((0, 7), (8, 11), (12, 15), (16, 19), (20, 22))
    # PBSS alert thresholds to evaluate as trading rules
    pbss_thresholds: tuple = (12, 14, 16, 18, 20)
    # Breadth (pct of universe above own 50DMA) regime cutoffs
    breadth_up: float = 55.0
    breadth_down: float = 45.0
    # Minimum symbols with valid 50DMA required to trust a breadth reading
    breadth_min_symbols: int = 200


# Columns required from daily snapshots for PBSS recomputation + analysis
FEATURE_COLUMNS = [
    "symbol",
    "close",
    "last",   # pre-2026-05 snapshots populate only `last`; close is coalesced from it
    "score",
    "vol_z20",
    "relvol20",
    "obv_above_ma",
    "obv_slope_10",
    "ret_5d",
    "ret_1w",
    "adx14",
    "rsi14",
    "proximity_52w_high_pct",
    "pivot_clear_pct",
    "n_consecutive_up",
    "median_traded_value_20d",
]

DEFAULT_CONFIG = BacktestConfig()
