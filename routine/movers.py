"""Top daily gainers/losers among liquid symbols.

INFORMATION, NOT SIGNALS. Measured on 91k liquid symbol-days: chasing the
day's big movers has no positive edge (see routine_config.MOVERS_NOTE).
The digest shows them for market awareness only.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

import pandas as pd

from . import fetch, routine_config

log = logging.getLogger(__name__)


def compute_movers(
    universe_df: pd.DataFrame,
    cfg: Optional[routine_config.DailyConfig] = None,
) -> Dict[str, List[Dict]]:
    """{'gainers': [...], 'losers': [...]} — top-N by 1-day % change among
    liquid (>= liquidity floor), non-penny symbols with >= 21 bars."""
    cfg = cfg or routine_config.DAILY
    rows: List[Dict] = []
    for row in universe_df.itertuples():
        sym = str(row.symbol).upper()
        if sym.startswith("^"):
            continue
        try:
            df = fetch.load_ohlcv(sym)
            if len(df) < 21:
                continue
            c = pd.to_numeric(df["close"], errors="coerce")
            v = pd.to_numeric(df["volume"], errors="coerce")
            c0, c1 = float(c.iloc[-2]), float(c.iloc[-1])
            if pd.isna(c0) or pd.isna(c1) or c0 <= 0 or c1 < cfg.movers_min_price:
                continue
            tv20 = float((c * v).tail(20).median())
            if pd.isna(tv20) or tv20 < cfg.liquidity_floor_rupees:
                continue
            v20 = float(v.tail(21).head(20).mean())
            relvol = round(float(v.iloc[-1]) / v20, 1) if v20 and v20 > 0 else 0.0
            rows.append(
                {
                    "symbol": sym,
                    "name": str(getattr(row, "name", sym)),
                    "close": round(c1, 2),
                    "chg_pct": round((c1 / c0 - 1.0) * 100.0, 1),
                    "relvol": relvol,
                }
            )
        except Exception as exc:
            log.warning("movers failed for %s: %s", sym, exc)
            continue
    n = cfg.movers_size
    by_chg = sorted(rows, key=lambda r: r["chg_pct"], reverse=True)
    gainers = [r for r in by_chg[:n] if r["chg_pct"] > 0]
    losers = [r for r in sorted(rows, key=lambda r: r["chg_pct"])[:n] if r["chg_pct"] < 0]
    return {"gainers": gainers, "losers": losers}
