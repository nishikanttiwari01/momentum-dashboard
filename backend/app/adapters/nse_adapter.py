from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
import random

def fetch_universe_rows(as_of: Optional[str], universe: Optional[List[str]]) -> List[Dict[str, Any]]:
    """
    Tiny NSE-like stub that produces a few rows deterministically enough for local testing.
    - If 'universe' passed, use those symbols; else use a fixed small basket.
    - Values are simple but plausible; each dict maps to a 'scores' Parquet row.
    """
    symbols = universe or ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ITC.NS"]
    ts = as_of or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    out: List[Dict[str, Any]] = []
    for s in symbols:
        base = abs(hash(s)) % 2000 + 100  # 100..2099
        last = round(base + random.random() * 10, 2)
        change_pct = round((random.random() - 0.5) * 2.0, 2)
        score = round(random.random(), 4)
        out.append(
            {
                "symbol": s,
                "name": s.split(".")[0].title(),
                "sector": "NSE",
                "last": last,
                "change_pct": change_pct,
                "score": score,
                "as_of": ts,
            }
        )
    return out
