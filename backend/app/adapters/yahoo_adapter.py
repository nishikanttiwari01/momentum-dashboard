import time, math
import yfinance as yf
from typing import Iterable, List, Dict, Any

# ... keep class YahooAdapter, __init__, _norm_sym as-is ...

def _retry(attempts=3, delay=0.8):
    def deco(fn):
        def wrap(*a, **k):
            last_exc = None
            for i in range(attempts):
                try:
                    return fn(*a, **k)
                except Exception as e:
                    last_exc = e
                    time.sleep(delay * (1 + i))
            raise last_exc
        return wrap
    return deco

class YahooAdapter:
    # keep __init__ and _norm_sym...

    @_retry(attempts=3, delay=0.6)
    def _fetch_one(self, sym: str) -> Dict[str, Any]:
        tk = yf.Ticker(sym)
        finfo = getattr(tk, "fast_info", None) or {}
        last = finfo.get("last_price")
        prev = finfo.get("previous_close") or finfo.get("last_close")

        # Fallback: 5d daily history
        if last is None or prev is None:
            hist = tk.history(period="5d", auto_adjust=False, interval="1d")
            if hist is not None and not hist.empty:
                last_row = hist.iloc[-1]
                last = float(last_row.get("Close")) if "Close" in last_row else last
                if len(hist) >= 2:
                    prev_row = hist.iloc[-2]
                    prev = float(prev_row.get("Close")) if "Close" in prev_row else prev

        change_pct = None
        if last is not None and prev not in (None, 0):
            try:
                change_pct = (float(last) - float(prev)) * 100.0 / float(prev)
            except Exception:
                change_pct = None

        return {
            "symbol": sym,
            "name": None,
            "sector": None,
            "last": float(last) if last is not None else None,
            "change_pct": float(change_pct) if change_pct is not None else None,
            "score": 0,
            "strength": None,
            "rsi": None, "adx": None,
            "ret_12_1m": None, "ret_6m": None, "ret_3m": None, "ret_1m": None,
            "ret_1w": None, "pct_from_52w_high": None, "atr_pct": None,
            "liquidity": None, "vol_spike": None, "pct_today": None,
            "buy": False, "reason": None, "source": "yahoo", "stale": False,
            "badges": [],
        }

    def fetch_quotes(self, symbols: Iterable[str]) -> List[Dict[str, Any]]:
        syms = [self._norm_sym(s) for s in symbols if s]
        out: List[Dict[str, Any]] = []
        for sym in syms:
            try:
                out.append(self._fetch_one(sym))
            except Exception:
                out.append({
                    "symbol": sym, "name": None, "sector": None,
                    "last": None, "change_pct": None, "score": 0,
                    "strength": None, "rsi": None, "adx": None,
                    "ret_12_1m": None, "ret_6m": None, "ret_3m": None, "ret_1m": None,
                    "ret_1w": None, "pct_from_52w_high": None, "atr_pct": None,
                    "liquidity": None, "vol_spike": None, "pct_today": None,
                    "buy": False, "reason": "fetch_error", "source": "yahoo", "stale": True,
                    "badges": [],
                })
            if self.throttle_sec:
                time.sleep(self.throttle_sec)
        return out
