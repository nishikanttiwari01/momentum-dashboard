from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import yfinance as yf

logger = logging.getLogger(__name__)


def _ema(values: List[float], period: int = 10) -> List[float]:
    """Compute an exponential moving average over the provided values."""
    if not values:
        return []
    alpha = 2 / (period + 1)
    out: List[float] = []
    e = None
    for v in values:
        e = v if e is None else (e + alpha * (v - e))
        out.append(float(e))
    return out


@dataclass
class CacheEntry:
    ts: datetime
    dates: List[str]
    closes: List[float]


class MarketDataRepo:
    """
    Small yfinance-based fetcher with an in-memory TTL cache.
    Provides sparkline-friendly data for the instruments detail endpoint.

    Methods expected by the detail service:
      - last_n_closes(symbol, run_id=None, n=30) -> List[float]
      - get_sparkline(symbol, run_id=None, n=30) -> Dict[str, List]

    Enhancements:
      * Returns aligned ISO dates along with prices.
      * Robust logging for cache hits/misses, fetch results, and exceptions.
      * Graceful fallback to cached stale data on fetch errors (if available).
      * Supports both "Adj Close" (preferred) and "Close".
      * Emits both plain keys ('prices','ema10','dates') and 30d keys
        ('prices_30d','ema10_30d','dates_30d') for maximum compatibility.
    """

    def __init__(
        self,
        ttl: timedelta = timedelta(minutes=10),
        cache_max_entries: int = 512,
    ) -> None:
        self._TTL = ttl
        self._cache_max = cache_max_entries
        # key: (SYMBOL, days) -> CacheEntry
        self._cache: Dict[Tuple[str, int], CacheEntry] = {}
        logger.debug(
            "MarketDataRepo initialized with TTL=%s, cache_max=%d",
            self._TTL,
            self._cache_max,
        )

    # ----------------------- internal helpers -----------------------

    def _trim_cache_if_needed(self) -> None:
        if len(self._cache) <= self._cache_max:
            return
        # drop the stalest half to keep memory in check
        items = sorted(self._cache.items(), key=lambda kv: kv[1].ts)
        drop = len(items) - self._cache_max // 2
        for k, _ in items[:drop]:
            self._cache.pop(k, None)
        logger.debug("Cache trimmed: kept=%d", len(self._cache))

    def _fetch(self, symbol: str, days: int) -> Tuple[List[str], List[float]]:
        symbol_u = symbol.upper()
        if symbol_u and not symbol_u.endswith(".NS"):
            symbol_u = f"{symbol_u}.NS"
        days = int(max(days, 60))  # ensure enough bars for weekends/holidays
        key = (symbol_u, days)
        now = datetime.utcnow()

        hit = self._cache.get(key)
        if hit and now - hit.ts < self._TTL:
            logger.debug(
                "Cache HIT for %s/%dd (age=%ss, points=%d)",
                symbol_u,
                days,
                int((now - hit.ts).total_seconds()),
                len(hit.closes),
            )
            return hit.dates, hit.closes

        logger.info("Fetching OHLCV: symbol=%s days=%d", symbol_u, days)
        try:
            df = yf.Ticker(symbol_u).history(
                period=f"{days}d",
                interval="1d",
                auto_adjust=False,
                actions=False,
            )
        except Exception as e:
            logger.exception("yfinance.history failed for %s: %s", symbol_u, e)
            if hit:
                logger.warning(
                    "Returning STALE cached data for %s due to fetch error.", symbol_u
                )
                return hit.dates, hit.closes
            return [], []

        if df is None or df.empty:
            logger.warning("Empty dataframe from yfinance for %s.", symbol_u)
            self._cache[key] = CacheEntry(now, [], [])
            return [], []

        # choose adjusted close if present
        col = "Adj Close" if "Adj Close" in df.columns else (
            "Close" if "Close" in df.columns else None
        )
        if not col:
            logger.error(
                "No Close/Adj Close column for %s dataframe columns=%s",
                symbol_u,
                list(df.columns),
            )
            self._cache[key] = CacheEntry(now, [], [])
            return [], []

        closes_series = df[col]
        mask = closes_series.notna()
        closes = [float(x) for x in closes_series[mask].tolist()]

        # extract ISO dates aligned to closes
        idx = df.index[mask]
        try:
            dates = [i.date().isoformat() for i in idx]
        except Exception:
            dates = [
                getattr(i, "date", lambda: i)().isoformat()
                if hasattr(i, "date")
                else str(i)
                for i in idx
            ]

        logger.info(
            "Fetched %d points for %s (from %s to %s).",
            len(closes),
            symbol_u,
            dates[0] if dates else "n/a",
            dates[-1] if dates else "n/a",
        )
        self._cache[key] = CacheEntry(now, dates, closes)
        self._trim_cache_if_needed()

        return dates, closes

    # ----------------------- public API -----------------------


    def get_sparkline(
        self, symbol: str, run_id: Optional[str] = None, n: int = 30
    ) -> dict:
        """
        Return a dict containing prices, dates, and EMA(10) for the last n points.
        Includes both generic keys and *_30d keys for compatibility.
        """
        dates, closes = self._fetch(symbol, max(n, 60))
        if not closes:
            logger.warning("get_sparkline: no data for symbol=%s", symbol)
            return {"prices": [], "ema10": [], "dates": []}

        prices = closes[-n:] if len(closes) >= n else closes
        dates_n = dates[-n:] if len(dates) >= n else dates
        ema10 = _ema(prices, 10)

        logger.debug(
            "get_sparkline: symbol=%s n=%d -> prices=%d, dates=%d",
            symbol,
            n,
            len(prices),
            len(dates_n),
        )

        return {
            "prices": prices,
            "ema10": ema10,
            "dates": dates_n,
            "prices_30d": prices,
            "ema10_30d": ema10,
            "dates_30d": dates_n,
        }
