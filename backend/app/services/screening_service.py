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

def _as_of_date_str(as_of_val: Optional[str]) -> Optional[str]:
    """
    Return YYYY-MM-DD if payload.as_of is present (date or ISO datetime),
    else None. Tolerant to '2025-09-21', '2025-09-21T10:00:00Z', etc.
    """
    if not as_of_val:
        return None
    s = str(as_of_val).strip()
    # if it's already a date string
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    try:
        return pd.to_datetime(s).strftime("%Y-%m-%d")
    except Exception:
        return None


# --------------------------- IO helpers -----------------------------

def _ensure_parquet_root() -> None:
    root = datasets.get_parquet_root()
    root.mkdir(parents=True, exist_ok=True)
    # truthy, once per process (datasets.py also logs root; duplicating here is intentional for service logs)
    try:
        log.info("parquet_root_resolved(service)", extra={"root": str(root.resolve())})
    except Exception:
        pass


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
    # NEW: ATR10% (tighter volatility proxy used by entry/exit heuristics)
    ind["atr10_pct"] = (atr(df["high"], df["low"], df["close"], 10) / df["close"]) * 100.0
    ind["relvol20"] = relvol(df["volume"], 20)
    ind["proximity_52w_high_pct"] = proximity_52w_high(df["close"], df["high"], 252)

    # NEW: Volume Z-score (20d)
    vol_ma20 = df["volume"].rolling(20, min_periods=20).mean()
    vol_sd20 = df["volume"].rolling(20, min_periods=20).std(ddof=0)
    ind["vol_z20"] = (df["volume"] - vol_ma20) / vol_sd20.replace(0.0, np.nan)

    # NEW: OBV block (level, MA, slope, above/under flag)
    _delta = df["close"].diff()
    _sgn = np.sign(_delta.fillna(0.0))
    obv = (df["volume"] * _sgn).fillna(0.0).cumsum()
    ind["obv"] = obv
    ind["obv_ma30"] = obv.rolling(30, min_periods=30).mean()
    ind["obv_slope_10"] = obv - obv.shift(10)
    ind["obv_above_ma"] = ind["obv"] > ind["obv_ma30"]

    # NEW: Pivot (prior 20d high), pivot clearance %, base length bars
    pivot_20d = df["high"].rolling(20, min_periods=20).max().shift(1)
    ind["pivot_20d"] = pivot_20d
    ind["pivot_clear_pct"] = (df["close"] / pivot_20d - 1.0) * 100.0
    # Base length: bars since last 20d high (tolerant to float noise)
    hh20 = df["high"].rolling(20, min_periods=20).max()
    is_new_high = df["high"] >= (hh20 * 0.999)
    _idx = np.arange(len(df))
    last_nh_idx = pd.Series(np.where(is_new_high, _idx, np.nan), index=df.index).ffill()
    ind["base_len_bars"] = (_idx - last_nh_idx).astype(float)

    # NEW: Behavior fields
    ind["gap_up_pct"] = (df["open"] / df["close"].shift(1) - 1.0) * 100.0
    rng = (df["high"] - df["low"])
    ind["close_pos_in_bar"] = np.where(rng > 0, (df["close"] - df["low"]) / rng, np.nan)

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
    vol_z20 = _maybe_float(r.get("vol_z20"))
    atr10_pct = _maybe_float(r.get("atr10_pct"))
    obv_val = _maybe_float(r.get("obv"))
    obv_ma30 = _maybe_float(r.get("obv_ma30"))
    obv_slope_10 = _maybe_float(r.get("obv_slope_10"))
    obv_above_ma = (bool(r.get("obv_above_ma")) if r.get("obv_above_ma") is not None else None)
    pivot_20d = _maybe_float(r.get("pivot_20d"))
    pivot_clear_pct = _maybe_float(r.get("pivot_clear_pct"))
    base_len_bars = _maybe_float(r.get("base_len_bars"))
    gap_up_pct = _maybe_float(r.get("gap_up_pct"))
    close_pos_in_bar = _maybe_float(r.get("close_pos_in_bar"))
    ret_1w = _maybe_float(r.get("ret_1w"))
    ret_1m = _maybe_float(r.get("ret_1m"))
    ret_3m = _maybe_float(r.get("ret_3m"))
    ret_6m = _maybe_float(r.get("ret_6m"))
    ret_12_1m = _maybe_float(r.get("ret_12_1m"))
    ema10 = _maybe_float(r.get("ema10"))
    ema50 = _maybe_float(r.get("ema50"))
    ema200 = _maybe_float(r.get("ema200"))
    atr14_pct = _maybe_float(r.get("atr14_pct"))

    # Derivations formerly placeholders → now from computed indicators
    is_new_52w_high = (prox_52w or -1) >= 0.0
    vol_z = vol_z20
    obv_slope_pos = (obv_slope_10 is not None and obv_slope_10 > 0)

    # Scores
    basic_raw, basic_pct, basic_badges = basic_score(
        rsi14, adx14, adx_s5, is_new_52w_high, pivot_clear_pct, base_len_bars,
        relvol20, vol_z, bool(obv_above_ma) if obv_above_ma is not None else False
    )
    # full_score may return None if inputs are incomplete (as per updated scoring.py)
    full_100, full_badges = full_score(
        rsi14, adx14, adx_s5, plus_di, minus_di,
        prox_52w, pivot_clear_pct, base_len_bars, 0,
        relvol20, vol_z, obv_above_ma or False, obv_slope_pos or False,
        None,  # delivery lift unknown
        6 if (ema50 or 0) > (ema200 or 0) else 3 if (ema200 or 0) < (last or 0) else 0,  # rough regime proxy
        2,  # sector RS placeholder
        atr10_pct=atr10_pct,
        gap_up_pct=gap_up_pct,
        close_pos_in_bar=close_pos_in_bar
    )

    # ---------- canonical scoring + fallback metadata ----------
    score_basic = basic_raw if basic_raw is not None else None
    score_basic_normalized = int(round(basic_pct)) if basic_pct is not None else None
    score_full = int(round(full_100)) if full_100 is not None else None

    full_required_keys = [
        "relvol20", "vol_z20", "obv", "obv_ma30", "obv_slope_10", "obv_above_ma",
        "pivot_20d", "pivot_clear_pct", "base_len_bars",
        "proximity_52w_high_pct", "atr14_pct", "ema10", "ema50", "ema200", "rsi14", "adx14"
    ]
    data_gaps: List[str] = []
    for k in full_required_keys:
        v = r.get(k)
        missing = False
        try:
            missing = (v is None) or (isinstance(v, (float, np.floating)) and (np.isnan(v) or np.isinf(v)))
        except Exception:
            missing = v is None
        if missing:
            data_gaps.append(k)

    score_source = "full"
    stale = False
    if score_full is not None and not data_gaps:
        score = int(score_full)
        score_source = "full"
        badges = (full_badges or [])
        recommendation, reason = recommendation_and_reason(
            score, rsi14, adx14, prox_52w, relvol20, pivot_clear_pct,
            atr14_pct=atr14_pct, atr10_pct=atr10_pct, gap_up_pct=gap_up_pct,
            close_pos_in_bar=close_pos_in_bar
        )
    else:
        score = score_basic_normalized if score_basic_normalized is not None else 0
        score_source = "basic_fallback"
        stale = True
        badges = (basic_badges or [])
        if not badges:
            badges = [{"category": "WATCH", "label": "⏳ Watch (data incomplete)"}]

        recommendation, reason = recommendation_and_reason(
            None, rsi14, adx14, prox_52w, relvol20, pivot_clear_pct
        )
        if data_gaps:
            reason = f"{reason} · missing: {', '.join(sorted(set(data_gaps)))}"

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
        "proximity_52w_high_pct": prox_52w,  # canonical
        "atr14_pct": atr14_pct,
        # persisted extras
        "atr10_pct": atr10_pct,
        "vol_z20": vol_z20,
        "obv": obv_val,
        "obv_ma30": obv_ma30,
        "obv_slope_10": obv_slope_10,
        "obv_above_ma": obv_above_ma,
        "pivot_20d": pivot_20d,
        "pivot_clear_pct": pivot_clear_pct,
        "base_len_bars": (int(round(base_len_bars)) if base_len_bars is not None else None),
        "gap_up_pct": gap_up_pct,
        "close_pos_in_bar": close_pos_in_bar,
        "ret_1w": ret_1w,
        "ret_1m": ret_1m,
        "ret_3m": ret_3m,
        "ret_6m": ret_6m,
        "ret_12_1m": ret_12_1m,
        # scores
        "score": score,
        "score_full": score_full,
        "score_basic": score_basic,
        "score_basic_normalized": score_basic_normalized,
        "score_source": score_source,
        "data_gaps": data_gaps,
        "stale": stale,
        "rules_version": "scores_v2",
        "score_scale": "0-100",
        "badges": badges,
        "recommendation": recommendation,
        "reason": reason,
        "as_of": as_of_iso,
        "run_id": run_id,
    }

    # === Back-fill legacy fields & small derivations ===
    row.setdefault("rsi", row.get("rsi14"))
    row.setdefault("adx", row.get("adx14"))
    row.setdefault("pct_from_52w_high", row.get("proximity_52w_high_pct"))
    row.setdefault("atr_pct", row.get("atr14_pct"))
    row.setdefault("pct_today", row.get("change_pct"))

    # Liquidity: 20d avg traded value (₹)
    if row.get("liquidity") is None:
        try:
            ser_liq = (df["close"] * df["volume"]).rolling(20, min_periods=5).mean()
            row["liquidity"] = float(ser_liq.iloc[-1]) if ser_liq.notna().any() else None
        except Exception:
            row["liquidity"] = None

    # Volume spike: z-score vs last 20d
    if row.get("vol_spike") is None:
        try:
            if "vol_z20" in ind.columns:
                row["vol_spike"] = float(ind["vol_z20"].iloc[-1])
            else:
                v = df["volume"]
                mu = v.rolling(20, min_periods=5).mean()
                sd = v.rolling(20, min_periods=5).std(ddof=0)
                z = (v - mu) / sd.replace(0.0, np.nan)
                row["vol_spike"] = float(z.iloc[-1]) if z.notna().any() else None
        except Exception:
            row["vol_spike"] = None

    # Strength label (simple ADX-based)
    if not row.get("strength"):
        adx_val = row.get("adx")
        if isinstance(adx_val, (int, float)):
            row["strength"] = "High" if adx_val >= 35 else ("Medium" if adx_val >= 20 else "Low")

    # Buy flag from score
    if row.get("buy") is None and isinstance(row.get("score"), (int, float)):
        row["buy"] = "Yes" if row["score"] >= 75 else "No"

    # --------- Badge policy (minimal changes, normalized) ----------
    badges_in: List[Any] = row.get("badges") or []

    # If no ACTION badge, append one based on score
    has_action = any(isinstance(b, dict) and b.get("category") == "ACTION" for b in badges_in)
    if not has_action and isinstance(row.get("score"), (int, float)):
        badges_in.append(
            {"category": "ACTION", "label": "✅ Buy"} if row["score"] >= 75
            else {"category": "ACTION", "label": "🕒 Watch"}
        )

    # Ensure a classification badge exists from {BREAKOUT, MOMENTUM, WATCH, IGNORE}
    cls_categories = {"BREAKOUT", "MOMENTUM", "WATCH", "IGNORE"}
    def _code_to_category(code: str) -> Optional[str]:
        c = (code or "").upper()
        if "BREAKOUT" in c: return "BREAKOUT"
        if "MOMENTUM" in c: return "MOMENTUM"
        if "WATCH" in c: return "WATCH"
        if "IGNORE" in c: return "IGNORE"
        return None

    has_classification = any(
        isinstance(b, dict) and str(b.get("category", "")).upper() in cls_categories
        for b in badges_in
    )
    if not has_classification:
        # Derive a simple classification if scoring didn't provide one
        if row["score"] is not None and row["score"] >= 85 and (rsi14 or 0) >= 60 and (adx14 or 0) >= 30 and (pivot_clear_pct or 0) >= 2.0:
            badges_in.append({"category": "BREAKOUT", "label": "💥 Very High Breakout"})
        elif row["score"] is not None and row["score"] >= 75:
            badges_in.append({"category": "MOMENTUM", "label": "🔥 High Momentum"})
        else:
            badges_in.append({"category": "WATCH", "label": "⏳ Watch"})

    # Normalize badge shape and also map legacy {code,text} to classification where possible
    norm_badges: List[Dict[str, str]] = []
    for b in badges_in:
        if isinstance(b, dict):
            label = b.get("label") or b.get("text") or b.get("code") or "Badge"
            category = b.get("category")
            if not category:
                cat_from_code = _code_to_category(str(b.get("code", "")))
                category = cat_from_code or "INFO"
            norm_badges.append({"category": str(category), "label": str(label)})
        else:
            norm_badges.append({"category": "INFO", "label": str(b)})

    row["badges"] = norm_badges

    return row


# --------------------------- main orchestration -------------------------------

def run_screening(*, session: Session, key: Optional[str], payload: Dict[str, Any]) -> Tuple[RunDetail, bool]:
    """
    NEW: Write to the **new layout only** (no legacy to avoid confusion):
      * daily/as_of=YYYY-MM-DD/run_id=...
      * intraday/date=YYYY-MM-DD/run_id=...
    When as_of is provided, slice price history to <= as_of for correct EOD.
    """
    _ensure_parquet_root()
    jobs = SqlJobsRepo(session)
    history = SqlHistoryRepo(session)

    # ---- make as_of ISO **timezone-aware** ----
    as_of_raw = payload.get("as_of")
    as_of_date = _as_of_date_str(as_of_raw)
    if as_of_date:
        # represent EOD with midnight UTC to keep tz-aware
        as_of_iso = f"{as_of_date}T00:00:00Z"
    elif as_of_raw:
        # coerce any datetime-ish string to UTC ISO
        try:
            as_of_iso = pd.to_datetime(as_of_raw, utc=True).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            as_of_iso = _utcnow_aware().isoformat().replace("+00:00", "Z")
    else:
        as_of_iso = _utcnow_aware().isoformat().replace("+00:00", "Z")

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
        try:
            log.info("screening_start", extra={"run_id": job.run_id, "as_of": as_of_iso, "universe": resolved_universe})
        except Exception:
            pass

        # Load universe
        symbols, _ = UniverseRepo().list_symbols(resolved_universe, page=1, per_page=999_999)
        if not symbols:
            symbols = list(_FALLBACK_NSE)
        symbols_processed = len(symbols)
        try:
            log.info("screening_universe", extra={"count": symbols_processed, "sample": symbols[:5]})
        except Exception:
            pass

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

            # --- as_of slicing for EOD/backfills ---
            df_eff = df
            if as_of_date:
                try:
                    cut = pd.to_datetime(as_of_date).date()
                    if not df.empty:
                        mask = pd.Series(df.index.date <= cut, index=df.index)
                        df_eff = df.loc[mask[mask].index]
                except Exception:
                    df_eff = df  # fallback

            # --- skip symbols with no prices ---
            if df_eff is None or df_eff.empty:
                log.warning("no prices for symbol; skipping row", extra={"symbol": sym, "as_of": as_of_iso})
                continue

            ind = _compute_indicators(df_eff)
            row = _make_scores_row(
                symbol=sym, name=q.get("name"), sector=q.get("sector"),
                as_of_iso=as_of_iso, run_id=job.run_id, df=df_eff, ind=ind
            )
            rows.append(row)

        rows_written = len(rows)
        try:
            log.info("scores_rows_built", extra={"rows": rows_written})
        except Exception:
            pass

        # ------------------- WRITE SNAPSHOTS (new layout only) -------------------
        datasets.write_schema_version("scores", 2)
        try:
            root = datasets.get_parquet_root().resolve()
        except Exception:
            root = None

        try:
            if as_of_date:
                # DAILY
                target = (root / "scores" / f"daily" / f"as_of={as_of_date}" / f"run_id={job.run_id}") if root else None
                log.info(
                    "scores_daily_precommit",
                    extra={"as_of": as_of_date, "run_id": job.run_id, "rows": rows_written, "target": str(target) if target else None}
                )
                w_daily = datasets.begin_atomic_write_scores_daily(as_of_date, job.run_id)
                w_daily.write_df(pa.Table.from_pylist(rows))
                w_daily.commit()
                snapshot_path = str(
                    (datasets.get_parquet_root()
                     / "scores" / "daily"
                     / f"as_of={as_of_date}"
                     / f"run_id={job.run_id}").resolve()
                )
                # post-commit quick listing
                try:
                    tgt = (datasets.get_parquet_root() / "scores" / "daily" / f"as_of={as_of_date}" / f"run_id={job.run_id}")
                    files = [p.name for p in tgt.glob("*.parquet")] if tgt.exists() else []
                    log.info("scores_daily_postcommit", extra={"target": str(tgt), "files": files})
                except Exception:
                    pass
                log.info("scores daily written", extra={"as_of": as_of_date, "run_id": job.run_id, "rows": rows_written})
            else:
                # INTRADAY
                today_str = _utcnow_aware().date().strftime("%Y-%m-%d")
                target = (root / "scores" / f"intraday" / f"date={today_str}" / f"run_id={job.run_id}") if root else None
                log.info(
                    "scores_intraday_precommit",
                    extra={"date": today_str, "run_id": job.run_id, "rows": rows_written, "target": str(target) if target else None}
                )
                w_intra = datasets.begin_atomic_write_scores_intraday(today_str, job.run_id)
                w_intra.write_df(pa.Table.from_pylist(rows))
                w_intra.commit()
                snapshot_path = str(
                    (datasets.get_parquet_root()
                     / "scores" / "intraday"
                     / f"date={today_str}"
                     / f"run_id={job.run_id}").resolve()
                )
                # post-commit quick listing
                try:
                    tgt = (datasets.get_parquet_root() / "scores" / "intraday" / f"date={today_str}" / f"run_id={job.run_id}")
                    files = [p.name for p in tgt.glob("*.parquet")] if tgt.exists() else []
                    log.info("scores_intraday_postcommit", extra={"target": str(tgt), "files": files})
                except Exception:
                    pass
                log.info("scores intraday written", extra={"date": today_str, "run_id": job.run_id, "rows": rows_written})
        except Exception:
            log.exception("snapshot write failed", extra={"run_id": job.run_id})
            raise

        # ------------------- END WRITES -------------------

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
