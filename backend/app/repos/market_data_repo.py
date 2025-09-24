from __future__ import annotations
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import yfinance as yf

class MarketDataRepo:
    """Small yfinance fetcher + 10-min in-memory cache to avoid rate limits."""
    _TTL = timedelta(minutes=10)

    def __init__(self) -> None:
        self._cache: Dict[Tuple[str, int], Tuple[datetime, List[float]]] = {}

    def _fetch(self, symbol: str, days: int) -> List[float]:
        key = (symbol.upper(), days)
        now = datetime.utcnow()
        hit = self._cache.get(key)
        if hit and now - hit[0] < self._TTL:
            return hit[1]
        period = f"{max(days, 60)}d"  # ensure enough bars for weekends/holidays
        try:
            df = yf.Ticker(symbol).history(period=period, interval="1d", auto_adjust=False)
        except Exception:
            df = None
        if df is None or df.empty:
            self._cache[key] = (now, [])
            return []
        closes = df["Adj Close"] if "Adj Close" in df.columns else df["Close"]
        out = [float(x) for x in closes.dropna().tolist()]
        self._cache[key] = (now, out)
        return out

    def last_n_closes(self, symbol: str, run_id: Optional[str] = None, n: int = 30) -> List[float]:
        xs = self._fetch(symbol, max(n, 60))
        return xs[-n:] if len(xs) >= n else xs

    def get_sparkline(self, symbol: str, run_id: Optional[str] = None, n: int = 30) -> dict:
        prices = self.last_n_closes(symbol, run_id, n)
        # EMA(10)
        ema, a, e = [], 2/(10+1), None
        for p in prices:
            e = p if e is None else (e + a*(p - e))
            ema.append(float(e))
        return {"prices": prices, "ema10": ema}
