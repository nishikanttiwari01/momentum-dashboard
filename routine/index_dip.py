"""Index mean-reversion signal (NIFTYBEES / BANKBEES dip-buying).

Rule measured on 2007-2026 history (routine/utils/index_dip_study.py, 19y):
BUY the index ETF at close when RSI(2) < 10 AND index above its 200DMA;
EXIT at the first close above entry, or after max_hold trading days.

The 200DMA gate is mandatory, not a preference: below it the same trade
measured ~zero-to-negative per trade with -19% (Nifty) to -22% (BankNifty)
worst-5-day tails. Above it: +0.35%/trade gross, 89% win, worst -5.6% (Nifty).

Position state is reconstructed deterministically from the price series
itself (entry = close of the last signal day; exit = first up-close), so no
database is needed and a missed day changes nothing.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import pandas as pd

from . import fetch, routine_config

log = logging.getLogger(__name__)


@dataclass
class DipStatus:
    index_name: str                 # NIFTY / BANKNIFTY
    etf: str                        # NIFTYBEES / BANKBEES
    label: str                      # BUY_TODAY | HOLD | EXIT_TODAY | NONE | OFF_SEASON | NO_DATA
    rsi2: Optional[float] = None
    above_200dma: Optional[bool] = None
    dma_gap_pct: Optional[float] = None   # close vs 200DMA, %
    entry: Optional[float] = None
    close: Optional[float] = None
    days_held: int = 0
    note: str = ""


def rsi(c: pd.Series, n: int = 2) -> pd.Series:
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def evaluate_series(
    closes: pd.Series,
    index_name: str,
    etf: str,
    cfg: Optional[routine_config.DailyConfig] = None,
) -> DipStatus:
    """Pure function: full close series in, today's dip status out."""
    cfg = cfg or routine_config.DAILY
    c = pd.to_numeric(closes, errors="coerce").dropna().reset_index(drop=True)
    if len(c) < cfg.dip_min_history:
        return DipStatus(index_name, etf, "NO_DATA",
                         note=f"only {len(c)} bars; need {cfg.dip_min_history}")

    r2 = rsi(c, 2)
    ma200 = c.rolling(200).mean()
    sig = ((r2 < cfg.dip_rsi2_max) & (c > ma200)).fillna(False).tolist()
    cv = c.tolist()

    # deterministic position reconstruction
    entry: Optional[float] = None
    opened = -1
    days = 0
    last_exit = -1
    exit_reason = ""
    for i in range(len(cv)):
        if entry is None:
            if sig[i]:
                entry, opened, days = cv[i], i, 0
        else:
            days += 1
            if cv[i] > entry:
                last_exit, exit_reason, entry = i, "first up-close", None
            elif days >= cfg.dip_max_hold_td:
                last_exit, exit_reason, entry = i, f"timeout {cfg.dip_max_hold_td} TD", None

    last = len(cv) - 1
    rsi_now = round(float(r2.iloc[-1]), 1) if not pd.isna(r2.iloc[-1]) else None
    above = bool(cv[last] > ma200.iloc[-1]) if not pd.isna(ma200.iloc[-1]) else None
    gap = round((cv[last] / float(ma200.iloc[-1]) - 1) * 100, 1) if not pd.isna(ma200.iloc[-1]) else None

    common = dict(rsi2=rsi_now, above_200dma=above, dma_gap_pct=gap, close=round(cv[last], 2))
    if entry is not None:
        if opened == last:
            return DipStatus(index_name, etf, "BUY_TODAY", entry=round(entry, 2),
                             note="signal fired at today's close", **common)
        return DipStatus(index_name, etf, "HOLD", entry=round(entry, 2), days_held=days,
                         note="exit at first close above entry", **common)
    if last_exit == last:
        return DipStatus(index_name, etf, "EXIT_TODAY", days_held=days,
                         note=f"exit: {exit_reason}", **common)
    if above is False:
        return DipStatus(index_name, etf, "OFF_SEASON",
                         note="below 200DMA: dip-buying measured negative here", **common)
    return DipStatus(index_name, etf, "NONE", note="no oversold signal", **common)


def compute_dip_statuses(cfg: Optional[routine_config.DailyConfig] = None) -> List[DipStatus]:
    out: List[DipStatus] = []
    for index_name, symbol, etf in (
        ("NIFTY", routine_config.NIFTY_SYMBOL, "NIFTYBEES"),
        ("BANKNIFTY", routine_config.BANKNIFTY_SYMBOL, "BANKBEES"),
    ):
        try:
            df = fetch.load_ohlcv(symbol)
            out.append(evaluate_series(df["close"] if len(df) else pd.Series(dtype=float),
                                       index_name, etf, cfg))
        except Exception as exc:
            log.warning("index dip failed for %s: %s", symbol, exc)
            out.append(DipStatus(index_name, etf, "NO_DATA", note=str(exc)[:80]))
    return out
