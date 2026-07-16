"""Market regime gate: Nifty vs 200DMA + slope, India VIX modifier.

Drives position sizing and the no-new-buys switch. Deliberately simple and
fully deterministic; revisit weights only via backtest evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from . import fetch, routine_config


@dataclass
class RegimeState:
    label: str                 # RISK_ON | CAUTION | RISK_OFF | UNKNOWN
    size_multiplier: float     # 1.0 / 0.5 / 0.0
    allow_new_buys: bool
    description: str


def _classify(close: float, dma200: float, slope20: float, vix: Optional[float]) -> RegimeState:
    above = close > dma200
    rising = slope20 > 0
    if above and rising:
        label, mult = "RISK_ON", 1.0
    elif above or rising:
        label, mult = "CAUTION", 0.5
    else:
        label, mult = "RISK_OFF", 0.0

    vix_note = ""
    if vix is not None and vix >= 22.0:
        # volatility shock: downgrade one level
        if label == "RISK_ON":
            label, mult = "CAUTION", 0.5
        elif label == "CAUTION":
            label, mult = "RISK_OFF", 0.0
        vix_note = f", VIX {vix:.1f} elevated"

    pct = (close / dma200 - 1.0) * 100.0
    desc = (
        f"Nifty {pct:+.1f}% vs 200DMA, 20d slope {'+' if slope20 > 0 else '-'}"
        f"{vix_note}"
    )
    return RegimeState(label, mult, mult > 0, desc)


def current_regime() -> RegimeState:
    nifty = fetch.load_ohlcv(routine_config.NIFTY_SYMBOL)
    if len(nifty) < 210:
        return RegimeState("UNKNOWN", 0.5, True, "insufficient Nifty history (<210 bars) — half size")
    close = pd.to_numeric(nifty["close"], errors="coerce")
    dma200 = close.rolling(200).mean()
    slope20 = dma200.iloc[-1] - dma200.iloc[-21] if len(dma200) >= 221 else 0.0

    vix_val: Optional[float] = None
    vix = fetch.load_ohlcv(routine_config.VIX_SYMBOL)
    if len(vix):
        vix_val = float(pd.to_numeric(vix["close"], errors="coerce").iloc[-1])

    return _classify(float(close.iloc[-1]), float(dma200.iloc[-1]), float(slope20), vix_val)
