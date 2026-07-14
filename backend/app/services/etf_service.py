# backend/app/services/etf_service.py
"""ETF momentum watch module.

Reads a curated ETF list from configs/etf_watch.yaml, fetches ~13 months of
daily closes per ETF from Yahoo Finance (ticker = NSE symbol + ".NS"),
computes trailing returns (1m/3m/6m/1y), distance from 52-week high and a
simple trend state (close > 50DMA > 200DMA), then ranks by the configured
momentum window.

Results are cached on disk (data/etf_cache/etf_snapshot.json) with a TTL so
the dashboard stays fast and degrades to stale data when offline. No
fabricated values: if Yahoo returns nothing for a symbol it is reported with
null metrics and an error note.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = _REPO_ROOT / "configs" / "etf_watch.yaml"
CACHE_DIR = _REPO_ROOT / "data" / "etf_cache"
CACHE_FILE = CACHE_DIR / "etf_snapshot.json"

_LOCK = threading.Lock()

# Trading-day offsets (approximate month = 21 trading days).
_TD_1M, _TD_3M, _TD_6M, _TD_1Y = 21, 63, 126, 252


def load_etf_config() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception:
        log.exception("etf_watch: failed to parse %s", CONFIG_PATH)
        return {}


def _ret(closes: List[float], n: int) -> Optional[float]:
    if len(closes) <= n:
        return None
    base = closes[-1 - n]
    if not base:
        return None
    return round((closes[-1] / base - 1.0) * 100.0, 2)


def _sma(closes: List[float], n: int) -> Optional[float]:
    if len(closes) < n:
        return None
    return sum(closes[-n:]) / n


def _compute_row(meta: Dict[str, Any], closes: List[float]) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "symbol": meta["symbol"],
        "name": meta.get("name") or meta["symbol"],
        "category": meta.get("category") or "OTHER",
        "last_price": None,
        "ret_1m_pct": None,
        "ret_3m_pct": None,
        "ret_6m_pct": None,
        "ret_1y_pct": None,
        "pct_from_52w_high": None,
        "trend": "unknown",
        "error": None,
    }
    if not closes:
        row["error"] = "no price data"
        return row

    last = closes[-1]
    row["last_price"] = round(last, 2)
    row["ret_1m_pct"] = _ret(closes, _TD_1M)
    row["ret_3m_pct"] = _ret(closes, _TD_3M)
    row["ret_6m_pct"] = _ret(closes, _TD_6M)
    row["ret_1y_pct"] = _ret(closes, _TD_1Y)

    hi_window = closes[-_TD_1Y:] if len(closes) > _TD_1Y else closes
    hi = max(hi_window)
    if hi:
        row["pct_from_52w_high"] = round((last / hi - 1.0) * 100.0, 2)

    sma50, sma200 = _sma(closes, 50), _sma(closes, 200)
    if sma50 is not None and sma200 is not None:
        row["trend"] = "up" if (last > sma50 > sma200) else ("down" if (last < sma50 < sma200) else "mixed")
    elif sma50 is not None:
        row["trend"] = "up" if last > sma50 else "down"
    return row


def _fetch_all(etfs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    import yfinance as yf

    tickers = {f"{e['symbol'].upper()}.NS": e for e in etfs if e.get("symbol")}
    rows: List[Dict[str, Any]] = []
    try:
        df = yf.download(
            list(tickers.keys()),
            period="400d",
            interval="1d",
            auto_adjust=True,
            actions=False,
            group_by="ticker",
            progress=False,
            threads=True,
        )
    except Exception:
        log.exception("etf_watch: batch download failed")
        df = None

    for tk, meta in tickers.items():
        closes: List[float] = []
        try:
            if df is not None and not df.empty:
                sub = df[tk]["Close"] if tk in getattr(df.columns, "levels", [[]])[0] else df["Close"]
                closes = [float(x) for x in sub.dropna().tolist()]
        except Exception:
            log.debug("etf_watch: no batch data for %s", tk, exc_info=True)
        if not closes:
            # per-ticker fallback
            try:
                h = yf.Ticker(tk).history(period="400d", interval="1d", auto_adjust=True, actions=False)
                if h is not None and not h.empty and "Close" in h.columns:
                    closes = [float(x) for x in h["Close"].dropna().tolist()]
            except Exception:
                log.debug("etf_watch: fallback fetch failed for %s", tk, exc_info=True)
        rows.append(_compute_row(meta, closes))
    return rows


def _read_cache() -> Optional[Dict[str, Any]]:
    try:
        if CACHE_FILE.exists():
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        log.debug("etf_watch: cache read failed", exc_info=True)
    return None


def _write_cache(payload: Dict[str, Any]) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(payload), encoding="utf-8")
    except Exception:
        log.debug("etf_watch: cache write failed", exc_info=True)


def build_snapshot(force_refresh: bool = False) -> Dict[str, Any]:
    cfg = load_etf_config()
    etfs = cfg.get("etfs") or []
    settings = cfg.get("etf_watch") or {}
    if not etfs:
        return {"configured": False, "etfs": []}

    ttl_s = float(settings.get("cache_ttl_hours") or 6) * 3600.0
    rank_by = str(settings.get("rank_by") or "ret_3m_pct")

    cached = _read_cache()
    if cached and not force_refresh:
        age = time.time() - float(cached.get("fetched_ts") or 0)
        if age < ttl_s:
            cached["stale"] = False
            return cached

    with _LOCK:
        try:
            rows = _fetch_all(etfs)
            ok = [r for r in rows if r.get("last_price") is not None]
            if not ok and cached:
                cached["stale"] = True
                return cached
        except Exception:
            log.exception("etf_watch: snapshot build failed")
            if cached:
                cached["stale"] = True
                return cached
            raise

    def _key(r: Dict[str, Any]):
        v = r.get(rank_by)
        return v if isinstance(v, (int, float)) else float("-inf")

    rows.sort(key=_key, reverse=True)
    payload = {
        "configured": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fetched_ts": time.time(),
        "rank_by": rank_by,
        "top_n": int(settings.get("top_n") or 8),
        "stale": False,
        "etfs": rows,
    }
    _write_cache(payload)
    return payload
