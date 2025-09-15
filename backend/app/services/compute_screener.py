# app/services/compute_screener.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, date, timezone
import pandas as pd

from app.domain.indicators import compute_indicators_for_panel
from app.domain.scoring import compute_score

@dataclass
class ComputeResult:
    rows: pd.DataFrame             # columns aligned to ScreenerRow
    as_of: datetime                # aware UTC
    run_id: str

def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

def build_screener_rows(
    candles: pd.DataFrame,
    instruments: pd.DataFrame,
    as_of_date: date,
    run_id: str,
) -> ComputeResult:
    """
    candles: MultiIndex [symbol, date] with cols open,high,low,close,adj_close,volume
    instruments: index=symbol with cols name, sector (optional)
    """
    if candles.empty:
        # Return empty but consistent
        return ComputeResult(rows=pd.DataFrame(), as_of=_aware(datetime.utcnow()), run_id=run_id)

    # compute indicators on full panel
    ind = compute_indicators_for_panel(candles)

    # take last available row per symbol as of as_of_date
    # (candles may include earlier dates for warmup)
    last_idx = candles.groupby(level=0).tail(1).index
    # Join base snapshot data
    base = candles.loc[last_idx, ["close", "volume"]].rename(columns={"close": "last"})
    joined = base.join(ind.loc[last_idx], how="left")

    # Rename columns to ScreenerRow fields
    out = pd.DataFrame(index=joined.index)
    out["last"] = joined["last"]
    out["change_pct"] = joined["pct_today"]
    out["wk_change"] = joined["wk_change"]
    out["wk_change_pct"] = joined["wk_change_pct"]
    out["rsi"] = joined["rsi14"]
    out["adx"] = joined["adx14"]
    out["atr_pct"] = joined["atr_pct"]
    out["vol_spike"] = joined["relvol20"]
    out["pct_from_52w_high"] = joined["proximity_52w_high_pct"]
    out["ret_12_1m"] = joined["ret_12_1m"]
    out["ret_6m"] = joined["ret_6m"]
    out["ret_3m"] = joined["ret_3m"]
    out["ret_1m"] = joined["ret_1m"]

    # Liquidity proxy (₹ Cr) ~ avg volume 20 * last / 1e7 (adjust per market)
    avg_vol20 = candles["volume"].groupby(level=0).rolling(20, min_periods=1).mean().reset_index(level=0, drop=True)
    avg20_last = avg_vol20.loc[last_idx]
    out["liquidity"] = (avg20_last * out["last"]) / 1e7

    # Score, strength, buy, reason, badges
    score_cols = out.join(joined[["last", "volume"]], how="left")
    score_pack = compute_score(score_cols)
    out = out.join(score_pack[["score", "strength", "buy", "reason"]])
    out["badges"] = score_pack["badges"]

    # Symbol/name/sector
    # derive the symbol from index level 0
    out = out.reset_index().rename(columns={"level_0": "symbol", "level_1": "last_index"})
    out["symbol"] = out["symbol"].astype(str)

    instruments = instruments.copy()
    instruments.index = instruments.index.astype(str)
    out = out.join(instruments[["name","sector"]], on="symbol", how="left")

    # Banner fields
    as_of_dt = _aware(datetime(as_of_date.year, as_of_date.month, as_of_date.day, 15, 30, 0, tzinfo=timezone.utc))
    out["as_of"] = as_of_dt
    out["run_id"] = run_id

    # Source & stale flags
    out["source"] = "scan"
    out["stale"] = False

    # Order columns roughly like ScreenerRow
    cols = [
        "symbol","name","sector","last","change_pct","wk_change","wk_change_pct",
        "badges","score","strength","rsi","adx","ret_12_1m","ret_6m","ret_3m","ret_1m",
        "pct_from_52w_high","atr_pct","liquidity","vol_spike","pct_today","buy","reason",
        "source","stale","run_id","as_of","last_index"
    ]
    out = out.reindex(columns=cols)

    return ComputeResult(rows=out, as_of=as_of_dt, run_id=run_id)
