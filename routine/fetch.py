"""EOD OHLCV fetcher with incremental parquet store.

One parquet per symbol under routine/routine_data/ohlcv/. Columns:
date, open, high, low, close, adj_close, volume. Downloader is injectable
so tests run offline; the default uses yfinance (works on the host machine).

CLI:
    python -m routine.fetch                 # incremental update, full universe
    python -m routine.fetch --limit 25      # first N symbols (smoke test)
    python -m routine.fetch --symbols RELIANCE TCS ^NSEI
"""
from __future__ import annotations

import argparse
import logging
import re
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional

import pandas as pd

from . import routine_config, universe

log = logging.getLogger(__name__)

Downloader = Callable[[List[str], date], Dict[str, pd.DataFrame]]

_SAFE = re.compile(r"[^A-Z0-9_^\-]")


def _path_for(symbol: str) -> Path:
    fname = _SAFE.sub("_", symbol.upper()).replace("^", "_IDX_") + ".parquet"
    return routine_config.OHLCV_DIR / fname


def load_ohlcv(symbol: str) -> pd.DataFrame:
    p = _path_for(symbol)
    if not p.exists():
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "adj_close", "volume"])
    df = pd.read_parquet(p)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df.sort_values("date").reset_index(drop=True)


def save_ohlcv(symbol: str, df: pd.DataFrame) -> None:
    routine_config.ensure_dirs()
    df = df.drop_duplicates(subset="date", keep="last").sort_values("date")
    df.to_parquet(_path_for(symbol), index=False)


def merge_new_bars(existing: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    if existing.empty:
        return new.reset_index(drop=True)
    combined = pd.concat([existing, new], ignore_index=True)
    combined = combined.drop_duplicates(subset="date", keep="last").sort_values("date")
    return combined.reset_index(drop=True)


def _yfinance_downloader(tickers: List[str], start: date) -> Dict[str, pd.DataFrame]:
    """Batch download via yfinance. Returns {ticker: normalized frame}."""
    import yfinance as yf  # imported lazily; not available in every sandbox

    raw = yf.download(
        tickers=" ".join(tickers),
        start=start.isoformat(),
        auto_adjust=False,
        group_by="ticker",
        progress=False,
        threads=True,
    )
    out: Dict[str, pd.DataFrame] = {}
    for t in tickers:
        try:
            sub = raw[t] if len(tickers) > 1 else raw
        except (KeyError, TypeError):
            continue
        if sub is None or sub.empty:
            continue
        df = pd.DataFrame(
            {
                "date": pd.to_datetime(sub.index).date,
                "open": sub["Open"].values,
                "high": sub["High"].values,
                "low": sub["Low"].values,
                "close": sub["Close"].values,
                "adj_close": sub.get("Adj Close", sub["Close"]).values,
                "volume": sub["Volume"].values,
            }
        )
        df = df.dropna(subset=["close"])
        if len(df):
            out[t] = df
    return out


def update_symbols(
    symbols: List[str],
    downloader: Optional[Downloader] = None,
    backfill_days: Optional[int] = None,
    today: Optional[date] = None,
) -> Dict[str, int]:
    """Incremental update. Returns {symbol: n_new_bars}. Never raises per-symbol;
    a symbol that fails is reported with -1 so the digest can surface it."""
    cfg = routine_config.DAILY
    downloader = downloader or _yfinance_downloader
    backfill_days = backfill_days or cfg.backfill_days
    today = today or date.today()
    routine_config.ensure_dirs()

    # group symbols by their fetch start date to batch efficiently
    plans: Dict[str, date] = {}
    for sym in symbols:
        existing = load_ohlcv(sym)
        if existing.empty:
            start = today - timedelta(days=backfill_days)
        else:
            start = existing["date"].max() + timedelta(days=1)
        if start <= today:
            plans[sym] = start

    results: Dict[str, int] = {s: 0 for s in symbols}
    todo = sorted(plans.items(), key=lambda kv: kv[1])
    for i in range(0, len(todo), cfg.batch_size):
        batch = todo[i : i + cfg.batch_size]
        start = min(d for _, d in batch)
        tickers = [universe.yahoo_ticker(s) for s, _ in batch]
        try:
            fetched = downloader(tickers, start)
        except Exception as exc:
            log.error("batch download failed (%d tickers): %s", len(tickers), exc)
            for s, _ in batch:
                results[s] = -1
            continue
        for sym, _ in batch:
            t = universe.yahoo_ticker(sym)
            new = fetched.get(t)
            if new is None or new.empty:
                results[sym] = results.get(sym) or 0
                continue
            existing = load_ohlcv(sym)
            merged = merge_new_bars(existing, new)
            n_new = len(merged) - len(existing)
            if n_new > 0:
                save_ohlcv(sym, merged)
            results[sym] = n_new
        time.sleep(0.5)  # be polite to the API
    return results


def freshness(symbols: List[str]) -> Optional[date]:
    """Newest bar date across sampled symbols (None if no data)."""
    newest: Optional[date] = None
    for sym in symbols[:20]:
        df = load_ohlcv(sym)
        if not df.empty:
            d = df["date"].max()
            newest = d if newest is None or d > newest else newest
    return newest


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="incremental EOD OHLCV fetch")
    p.add_argument("--symbols", nargs="+", help="explicit symbols (default: universe)")
    p.add_argument("--limit", type=int, help="only first N universe symbols")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if args.symbols:
        syms = [s.upper() for s in args.symbols]
    else:
        syms = universe.load_universe()["symbol"].tolist()
        if args.limit:
            syms = syms[: args.limit]
        syms += [routine_config.NIFTY_SYMBOL, routine_config.VIX_SYMBOL]

    res = update_symbols(syms)
    ok = sum(1 for v in res.values() if v >= 0)
    new = sum(v for v in res.values() if v > 0)
    fail = [s for s, v in res.items() if v < 0]
    print(f"updated {ok}/{len(res)} symbols, {new} new bars, failures: {len(fail)}")
    if fail:
        print("failed:", fail[:20])
    return 1 if len(fail) > len(res) // 2 else 0


if __name__ == "__main__":
    raise SystemExit(main())
