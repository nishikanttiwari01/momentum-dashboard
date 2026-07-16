"""Phase-2 runtime configuration (daily routine).

Secrets (SMTP creds, recipient) come ONLY from environment / .env file.
Everything tunable lives here with backtest-validated defaults.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from . import config as base_config

ROUTINE_DATA = base_config.ROUTINE_DIR / "routine_data"
OHLCV_DIR = ROUTINE_DATA / "ohlcv"
DB_PATH = ROUTINE_DATA / "routine.db"
OUT_DIR = ROUTINE_DATA / "out"

NIFTY_SYMBOL = "^NSEI"
BANKNIFTY_SYMBOL = "^NSEBANK"
VIX_SYMBOL = "^INDIAVIX"


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


@dataclass
class DailyConfig:
    # --- signal thresholds (corrected backtest, 2025-06 -> 2026-06; PLAN.md) ---
    # Best measured rule: PBSS>=18 AND score>=79 -> +4.1% fwd21 mean, 55% win
    # (vs +0.2% baseline). PBSS alone at 18 is marginal; the ELITE score gate
    # is what removes the junk. Regime gate (regime.py) adds further edge:
    # the same signals in a DOWN market averaged -2.6%.
    pbss_watch: int = 18
    pbss_conviction: int = 20
    min_score: int = 79
    liquidity_floor_rupees: float = 10_000_000.0
    max_ideas: int = 3
    cooldown_days: int = 5        # don't re-alert same symbol within N TD

    # --- position sizing ---
    capital_rupees: float = 500_000.0     # override: ROUTINE_CAPITAL
    risk_pct_per_trade: float = 1.0       # override: ROUTINE_RISK_PCT
    stop_atr_mult: float = 2.0
    t1_gain_pct: float = 10.0
    t2_gain_pct: float = 20.0
    timeout_days: int = 20                # exit stale positions

    # --- watchlist / movers (informational sections; never trade signals) ---
    watchlist_pbss_min: int = 15      # collect near-misses from this PBSS
    watchlist_score_min: int = 70     # ... or from this composite score
    watchlist_size: int = 5
    movers_size: int = 5
    movers_min_price: float = 20.0    # skip penny stocks in movers table

    # --- index dip (mean reversion on NIFTYBEES/BANKBEES; separate capital) ---
    dip_rsi2_max: float = 10.0        # entry: RSI(2) below this ...
    dip_max_hold_td: int = 10         # ... exit: first up-close or this timeout
    dip_min_history: int = 210        # bars needed for a valid 200DMA gate

    # --- data ---
    backfill_days: int = 420              # calendar days of history on first run
    min_history_rows: int = 240           # need this many bars to screen a symbol
    batch_size: int = 50                  # yfinance batch download size
    stale_data_max_age_days: int = 4      # digest screams if data older than this

    def __post_init__(self) -> None:
        self.capital_rupees = _env_float("ROUTINE_CAPITAL", self.capital_rupees)
        self.risk_pct_per_trade = _env_float("ROUTINE_RISK_PCT", self.risk_pct_per_trade)


DAILY = DailyConfig()

# Measured backtest results (corrected run, 2025-06 -> 2026-06, 223 signal
# days, cooldown + Rs 1cr liquidity floor), quoted in the digest instead of
# made-up numbers. Columns: rule, n, fwd21 mean, fwd21 median, win rate, >=10% hits.
MEASURED_STATS = [
    ("PBSS>=18 & score>=79 (the alert rule)", 313, "+4.1%", "+1.6%", "55%", "27%"),
    ("PBSS>=20 alone", 255, "+2.1%", "+0.3%", "50%", "26%"),
    ("all liquid stocks (baseline)", 262094, "+0.2%", "-1.2%", "45%", "18%"),
]


def load_dotenv(path: Path | None = None) -> None:
    """Tiny .env loader (no dependency). Existing env vars win."""
    p = path or (base_config.REPO_ROOT / ".env")
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def ensure_dirs() -> None:
    for d in (ROUTINE_DATA, OHLCV_DIR, OUT_DIR):
        d.mkdir(parents=True, exist_ok=True)


# Measured on 91,083 liquid symbol-days (Aug 2024 - Jul 2026, routine OHLCV
# store): chasing movers has NO positive edge. Quoted in the digest so the
# movers table is never mistaken for a signal.
MOVERS_NOTE = (
    "Measured (91k liquid symbol-days, Aug'24-Jul'26): buying the day's top-10 gainers "
    "returned +0.2% over 21 TD vs +2.3% baseline (all liquid stocks) - a measured NEGATIVE "
    "relative edge; next-day median -0.1%, win 47%. Stocks down -10% kept falling next day "
    "(-1.2% avg). A big gainer repeats in the next day's top-10 ~19% of the time, but you "
    "cannot know which one. This table is context, not signals."
)

# Index dip rule, measured 2007-2026 (~19y, routine/utils/index_dip_study.py).
INDEX_DIP_STATS = (
    "Measured 2007-2026: RSI(2)<10 & above 200DMA, exit first up-close (max 10 TD) - "
    "Nifty +0.35%/trade gross, win 89%, worst 5d -5.6%, ~17 trades/yr; BankNifty +0.25%, "
    "win 86%, worst -8.2%. BELOW the 200DMA the same trade measured ~0 to negative with "
    "-19% to -22% tails - the gate is mandatory. ETF costs ~0.1%/round trip. "
    "Separate capital bucket from the stock momentum system."
)
