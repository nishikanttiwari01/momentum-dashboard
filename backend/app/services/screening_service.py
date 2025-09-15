# backend/app/services/screening_service.py
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, Tuple, Dict, Any, List
import logging

import pyarrow as pa
import pandas as pd
import numpy as np
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy.orm import Session

from app.repos.sql.jobs_repo import SqlJobsRepo
from app.repos.sql.history_repo import SqlHistoryRepo
from app.repos.parquet import datasets

# Contract-first models (generated)
from app.schemas.runs import RunDetail, Counts

from app.core import config as app_config
from app.repos.parquet.universe_repo import UniverseRepo
from app.adapters.yahoo_adapter import YahooAdapter  # ctor takes NO args

import yfinance as yf

# Phase 11 domain helpers (vectorized)
from app.domain.indicators import (
    ema, rsi, adx, atr, relvol, proximity_52w_high, returns_block
)
from app.domain.scoring import basic_score, full_score, recommendation_and_reason

log = logging.getLogger(__name__)

_ALLOWED_PRESETS = {"NIFTY50", "NIFTY100", "NIFTY500", "MIDCAP", "SMALLCAP", "ALL"}
_FALLBACK_NSE = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS"]


# --------------------------- time helpers ---------------------------

def _utcnow_aware() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)

def _to_aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# --------------------------- IO helpers -----------------------------

def _ensure_parquet_root() -> None:
    root = datasets.get_parquet_root()
    root.mkdir(parents=True, exist_ok=True)


def _history_df(symbol: str, period: str = "400d") -> pd.DataFrame:
    """
    Pull ~18 months of daily candles (adj close, ohlc, volume) for indicators.
    We use yfinance directly here to keep adapter changes minimal.
    """
    try:
        t = yf.Ticker(symbol)
        df = t.history(period=period, interval="1d", auto_adjust=False)
    except Exception:
        df = None
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.rename(columns=str.lower)
    # normalize core columns
    for need in ["open", "high", "low", "close", "volume"]:
        if need not in df.columns:
            df[need] = np.nan
    # adj close if present; else fallback to close
    if "adj close" in df.columns:
        df["adj_close"] = df["adj close"].astype(float)
    else:
        df["adj_close"] = df["close"].astype(float)
    return df


# ---------------------- indicators computation ----------------------

def _compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute all indicators used by the Screener at the row's as_of.
    """
    ind = pd.DataFrame(index=df.index)
    ind["ema10"] = ema(df["close"], 10)
    ind["ema50"] = ema(df["close"], 50)
    ind["ema200"] = ema(df["close"], 200)

    ind["rsi14"] = rsi(df["close"], 14)

    adx_df = adx(df["high"], df["low"], df["close"], 14)
    ind["adx14"] = adx_df["adx"]
    ind["plus_di"] = adx_df["plus_di"]
    ind["minus_di"] = adx_df["minus_di"]
    ind["adx_slope_5"] = adx_df["adx_slope_5"]

    ind["atr14_pct"] = (atr(df["high"], df["low"], df["close"], 14) / df["close"]) * 100.0
    ind["relvol20"] = relvol(df["volume"], 20)
    ind["proximity_52w_high_pct"] = proximity_52w_high(df["close"], df["high"], 252)

    rets = returns_block(df["adj_close"])
    ind = ind.join(rets, how="left")
    return ind


# ---------------------- row construction ---------------------------

def _maybe_float(v):
    try:
        if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
            return None
        return float(v)
    except Exception:
        return None


def _make_scores_row(
    *,
    symbol: str,
    name: Optional[str],
    sector: Optional[str],
    as_of_iso: str,
    run_id: str,
    df: pd.DataFrame,
    ind: pd.DataFrame,
) -> Dict[str, Any]:
    """
    Build the final Screener row for this symbol.
    Includes indicators, returns, badges, recommendation, and both Full/Basic scores.
    """
    last = float(df["close"].iloc[-1]) if not df.empty else None
    prev = float(df["close"].iloc[-2]) if len(df) >= 2 else None
    change_pct = ((last - prev) * 100.0 / prev) if (last is not None and prev not in (None, 0)) else None

    r = ind.iloc[-1].to_dict() if not ind.empty else {}
    rsi14 = _maybe_float(r.get("rsi14"))
    adx14 = _maybe_float(r.get("adx14"))
    adx_s5 = _maybe_float(r.get("adx_slope_5"))
    plus_di = _maybe_float(r.get("plus_di"))
    minus_di = _maybe_float(r.get("minus_di"))
    relvol20 = _maybe_float(r.get("relvol20"))
    prox_52w = _maybe_float(r.get("proximity_52w_high_pct"))
    ret_1w = _maybe_float(r.get("ret_1w"))
    ret_1m = _maybe_float(r.get("ret_1m"))
    ret_3m = _maybe_float(r.get("ret_3m"))
    ret_6m = _maybe_float(r.get("ret_6m"))
    ret_12_1m = _maybe_float(r.get("ret_12_1m"))
    ema10 = _maybe_float(r.get("ema10"))
    ema50 = _maybe_float(r.get("ema50"))
    ema200 = _maybe_float(r.get("ema200"))
    atr14_pct = _maybe_float(r.get("atr14_pct"))

    # Minimal breakout/pivot placeholders (can be replaced with real pivot logic)
    is_new_52w_high = (prox_52w or -1) >= 0.0
    pivot_clear_pct = 0.0
    base_len_bars = 10
    vol_z = None
    obv_above_ma = None
    obv_slope_pos = None

    # Scores
    basic_raw, basic_pct, basic_badges = basic_score(
        rsi14, adx14, adx_s5, is_new_52w_high, pivot_clear_pct, base_len_bars,
        relvol20, vol_z, bool(obv_above_ma) if obv_above_ma is not None else False
    )
    full_100, full_badges = full_score(
        rsi14, adx14, adx_s5, plus_di, minus_di,
        prox_52w, pivot_clear_pct, base_len_bars, 0,
        relvol20, vol_z, obv_above_ma or False, obv_slope_pos or False,
        None,  # delivery lift unknown
        6 if (ema50 or 0) > (ema200 or 0) else 3 if (ema200 or 0) < (last or 0) else 0,  # rough regime proxy
        2   # sector RS placeholder
    )

    # Canonical score = Full or Basic%; also persist both
    score_basic = int(round(basic_pct)) if basic_pct is not None else None
    score_full = int(round(full_100)) if full_100 is not None else None
    score = score_full if score_full is not None else score_basic if score_basic is not None else 0

    badges = (full_badges or []) + (basic_badges or [])
    recommendation, reason = recommendation_and_reason(score, rsi14, adx14, prox_52w, relvol20, pivot_clear_pct)

    row: Dict[str, Any] = {
        "symbol": symbol,
        "name": name,
        "sector": sector,
        "last": last,
        "change_pct": change_pct,
        "rsi14": rsi14,
        "adx14": adx14,
        "ema10": ema10,
        "ema50": ema50,
        "ema200": ema200,
        "relvol20": relvol20,
        "proximity_52w_high_pct": prox_52w,  # CHANGED: use canonical field name
        "atr14_pct": atr14_pct,
        "ret_1w": ret_1w,
        "ret_1m": ret_1m,
        "ret_3m": ret_3m,
        "ret_6m": ret_6m,
        "ret_12_1m": ret_12_1m,
        "score": score,                 # canonical, used for default sort
        "score_full": score_full,       # CHANGED: persist both
        "score_basic": score_basic,     # CHANGED: persist both
        "score_scale": "0-100",
        "badges": badges,
        "recommendation": recommendation,
        "reason": reason,
        "as_of": as_of_iso,
        "run_id": run_id,
    }
    return row


# --------------------------- main orchestration -------------------------------

def run_screening(*, session: Session, key: Optional[str], payload: Dict[str, Any]) -> Tuple[RunDetail, bool]:
    """
    Phase 11: Single dataset 'scores/' (schema_version=2) with full columns.
    Writes one atomic snapshot; no more scores_v2/.
    """
    _ensure_parquet_root()
    jobs = SqlJobsRepo(session)
    history = SqlHistoryRepo(session)

    as_of_iso = (payload.get("as_of") or _utcnow_aware().isoformat().replace("+00:00", "Z"))
    universe = None
    if isinstance(payload.get("universe"), str):
        uni = payload["universe"].strip().upper()
        universe = uni if uni in _ALLOWED_PRESETS else None

    job, created = jobs.create_or_get_by_key(name="manual_scan", key=key, with_created=True)
    if not created:
        # idempotent replay: return prior run
        return (
            RunDetail(
                run_id=job.run_id,
                job_name=getattr(job, "name", None),
                status=job.status,
                started_at=_to_aware(job.started_at),
                ended_at=_to_aware(job.ended_at),
                counts=Counts(symbols_processed=None, rows_written=None),
                duration_ms=None,
                key=getattr(job, "key", None),
                snapshot_path=None,
                error=None,
                error_json=getattr(job, "error", None) if isinstance(getattr(job, "error", None), dict) else None,
            ),
            False,
        )

    symbols_processed = 0
    rows_written = 0
    snapshot_path = None

    try:
        cfg = app_config.load()
        resolved_universe = (
            (universe or "").strip().upper()
            or (getattr(cfg.scheduler, "universe", None) or "").strip().upper()
            or (getattr(cfg.screener, "default_universe", "NIFTY50") or "").strip().upper()
        )

        # Load universe
        symbols, _ = UniverseRepo().list_symbols(resolved_universe, page=1, per_page=999_999)
        if not symbols:
            symbols = list(_FALLBACK_NSE)
        symbols_processed = len(symbols)

        # Name & sector via YahooAdapter (best-effort)
        ya = YahooAdapter()
        try:
            quotes = {q["symbol"]: q for q in (ya.fetch_quotes(symbols) or [])}
        except Exception:
            quotes = {}

        # Compute full rows
        rows: List[Dict[str, Any]] = []
        for sym in symbols:
            df = _history_df(sym, period="400d")
            q = quotes.get(sym, {})
            if df.empty:
                # still emit a stub row (with name/sector if known)
                rows.append({
                    "symbol": sym, "name": q.get("name"), "sector": q.get("sector"),
                    "last": None, "change_pct": None,
                    "rsi14": None, "adx14": None, "ema10": None, "ema50": None, "ema200": None,
                    "relvol20": None, "proximity_52w_high_pct": None, "atr14_pct": None,
                    "ret_1w": None, "ret_1m": None, "ret_3m": None, "ret_6m": None, "ret_12_1m": None,
                    "score": 0, "score_full": None, "score_basic": None, "score_scale": "0-100",
                    "badges": [], "recommendation": "No", "reason": "",
                    "as_of": as_of_iso, "run_id": job.run_id,
                })
                continue

            ind = _compute_indicators(df)
            row = _make_scores_row(
                symbol=sym, name=q.get("name"), sector=q.get("sector"),
                as_of_iso=as_of_iso, run_id=job.run_id, df=df, ind=ind
            )
            rows.append(row)

        # Write the single consolidated dataset: scores/ (schema v2)
        datasets.write_schema_version("scores", 2)  # CHANGED: single dataset with v2 schema
        w = datasets.begin_atomic_write("scores", job.run_id)
        try:
            w.write_df(pa.Table.from_pylist(rows))
            w.commit()
            rows_written = len(rows)
            snapshot_path = str((datasets.get_parquet_root() / "scores" / f"run_id={job.run_id}").resolve())
        except Exception:
            try:
                w.abort()
            except Exception:
                pass
            raise

        # Mark success + write history (best-effort)
        jobs.complete_run(run_id=job.run_id, status="SUCCEEDED", error=None)
        try:
            history.insert_run_summary(run_id=job.run_id, as_of=as_of_iso, rows=rows_written)
        except Exception:
            pass

        return (
            RunDetail(
                run_id=job.run_id,
                job_name="manual_scan",
                status="SUCCEEDED",
                started_at=_to_aware(job.started_at),
                ended_at=_utcnow_aware(),
                counts=Counts(symbols_processed=symbols_processed, rows_written=rows_written),
                duration_ms=None,
                key=getattr(job, "key", None),
                snapshot_path=snapshot_path,
                error=None,
                error_json=None,
            ),
            True,
        )

    except StarletteHTTPException:
        jobs.fail_run(run_id=job.run_id, error="screening_service raised HTTPException")
        raise
    except Exception as exc:
        jobs.fail_run(run_id=job.run_id, error=f"screening_service failed: {exc}")
        raise StarletteHTTPException(
            status_code=500,
            detail={"code": "INTERNAL_ERROR", "detail": f"screening_service failed: {exc}"},
        )
