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
from app.domain.indicators import compute_indicator_frame
from app.domain.scoring import compute_score
from app.domain.rules.next_action import global_pre_gates

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


def _find_committed_run_for_as_of(as_of_date: str) -> Optional[str]:
    # Return the run_id of a committed daily snapshot for the given as_of, if any.
    try:
        as_of_root = datasets.scores_daily_dir(as_of_date)
        cands = []
        for child in as_of_root.glob("run_id=*"):
            if child.is_dir() and (child / "_SUCCESS").exists():
                rid = child.name.split("run_id=", 1)[-1]
                cands.append(rid)
        return sorted(cands)[-1] if cands else None
    except Exception:
        return None

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
    return compute_indicator_frame(df)


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
    # Build the final Screener row for this symbol (spec 2025-10-12A).
    last = float(df["close"].iloc[-1]) if not df.empty else None
    prev = float(df["close"].iloc[-2]) if len(df) >= 2 else None
    change_pct = ((last - prev) * 100.0 / prev) if (last is not None and prev not in (None, 0)) else None

    r = ind.iloc[-1].to_dict() if not ind.empty else {}
    rsi14 = _maybe_float(r.get("rsi14"))
    adx14 = _maybe_float(r.get("adx14"))
    relvol20 = _maybe_float(r.get("relvol20"))
    prox_52w = _maybe_float(r.get("proximity_52w_high_pct"))
    vol_z20 = _maybe_float(r.get("vol_z20"))
    atr10_pct = _maybe_float(r.get("atr10_pct"))
    obv_val = _maybe_float(r.get("obv"))
    obv_ma30 = _maybe_float(r.get("obv_ma30"))
    obv_slope_10 = _maybe_float(r.get("obv_slope_10"))
    obv_above_ma = (bool(r.get("obv_above_ma")) if r.get("obv_above_ma") is not None else None)
    pivot_high_20 = _maybe_float(r.get("pivot_high_20"))
    pivot_clear_pct = _maybe_float(r.get("pivot_clear_pct"))
    base_len_bars = _maybe_float(r.get("base_len_bars"))
    gap_up_pct = _maybe_float(r.get("gap_up_pct"))
    close_pos_in_bar = _maybe_float(r.get("close_pos_in_bar"))
    median_traded_value_20d = _maybe_float(r.get("median_traded_value_20d"))
    delivery_ratio_20d = _maybe_float(r.get("delivery_ratio_20d"))
    n_consecutive_up = _maybe_float(r.get("n_consecutive_up"))
    n_consecutive_down = _maybe_float(r.get("n_consecutive_down"))
    recent_failed_breakout_10d = bool(r.get("recent_failed_breakout_10d")) if r.get("recent_failed_breakout_10d") is not None else None
    adx_slope_pos = bool(r.get("adx_slope_pos")) if r.get("adx_slope_pos") is not None else None
    high_252 = _maybe_float(r.get("high_252"))
    ret_1w = _maybe_float(r.get("ret_1w"))
    ret_1m = _maybe_float(r.get("ret_1m"))
    ret_3m = _maybe_float(r.get("ret_3m"))
    ret_6m = _maybe_float(r.get("ret_6m"))
    ret_12_1m = _maybe_float(r.get("ret_12_1m"))
    ret_5d = _maybe_float(r.get("ret_5d"))
    ema10 = _maybe_float(r.get("ema10"))
    ema50 = _maybe_float(r.get("ema50"))
    ema200 = _maybe_float(r.get("ema200"))
    atr14_pct = _maybe_float(r.get("atr14_pct"))
    breadth_pct_50dma = _maybe_float(r.get("breadth_pct_50dma"))
    nifty_regime = r.get("nifty_regime")
    mansfield_rs_52 = _maybe_float(r.get("mansfield_rs_52"))
    asm_gsm_flags = r.get("asm_gsm_flags")
    upper_circuit_hits_60d = _maybe_float(r.get("upper_circuit_hits_60d"))

    score_inputs = {
        "proximity_52w_high_pct": prox_52w,
        "ret_5d": ret_5d if ret_5d is not None else ret_1w,
        "ret_1m": ret_1m,
        "ret_1w": ret_1w,
        "relvol20": relvol20,
        "vol_z20": vol_z20,
        "obv_above_ma": obv_above_ma,
        "obv_slope_10": obv_slope_10,
        "close": last,
        "ema10": ema10,
        "ema50": ema50,
        "ema200": ema200,
        "rsi14": rsi14,
        "adx14": adx14,
        "adx_slope_pos": adx_slope_pos,
        "mansfield_rs_52": mansfield_rs_52,
        "breadth_pct_50dma": breadth_pct_50dma,
        "delivery_ratio_20d": delivery_ratio_20d,
        "nifty_regime": nifty_regime,
        "gap_up_pct": gap_up_pct,
        "close_pos_in_bar": close_pos_in_bar,
        "pivot_clear_pct": pivot_clear_pct,
        "n_consecutive_up": n_consecutive_up,
        "n_consecutive_down": n_consecutive_down,
    }
    score_bundle = compute_score(score_inputs)

    score_basic = score_bundle.score_basic
    score_basic_normalized = score_basic
    score_full = score_bundle.score_full
    badges = score_bundle.badges or []

    full_required_keys = [
        "relvol20", "vol_z20", "obv", "obv_ma30", "obv_slope_10", "obv_above_ma",
        "pivot_high_20", "pivot_clear_pct", "base_len_bars",
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
    else:
        score = int(score_basic) if score_basic is not None else 0
        stale = True
        score_source = "basic_fallback" if score_full is None else "full_incomplete"

    if not badges:
        badges = [{"category": "WATCH", "label": "Watch (data incomplete)"}]

    reason_codes = list(score_bundle.reason_codes)
    if data_gaps:
        reason_codes.extend(f"missing:{gap}" for gap in sorted(set(data_gaps)))

    recommendation = "Yes" if score >= 70 else "No"
    reason = " | ".join(reason_codes[:6]) if reason_codes else score_bundle.band

    components = score_bundle.components
    score_breakdown = {
        "proximity": round(components.proximity, 2),
        "returns": round(components.returns, 2),
        "accumulation": round(components.accumulation, 2),
        "trend": round(components.trend, 2),
        "context": round(components.context, 2),
        "delivery_bonus": round(components.delivery_bonus, 2),
    }
    penalties_map = {k: round(v, 2) for k, v in components.penalties.items()}

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
        "relvol20_raw": _maybe_float(r.get("relvol20_raw")),
        "proximity_52w_high_pct": prox_52w,
        "atr14_pct": atr14_pct,
        "atr10_pct": atr10_pct,
        "vol_z20": vol_z20,
        "high_252": high_252,
        "obv": obv_val,
        "obv_ma30": obv_ma30,
        "obv_slope_10": obv_slope_10,
        "obv_above_ma": obv_above_ma,
        "pivot_high_20": pivot_high_20,
        "pivot_20d": pivot_high_20,
        "pivot_clear_pct": pivot_clear_pct,
        "base_len_bars": (int(round(base_len_bars)) if base_len_bars is not None else None),
        "gap_up_pct": gap_up_pct,
        "close_pos_in_bar": close_pos_in_bar,
        "median_traded_value_20d": median_traded_value_20d,
        "delivery_ratio_20d": delivery_ratio_20d,
        "n_consecutive_up": (int(n_consecutive_up) if n_consecutive_up is not None else None),
        "n_consecutive_down": (int(n_consecutive_down) if n_consecutive_down is not None else None),
        "recent_failed_breakout_10d": recent_failed_breakout_10d,
        "adx_slope_pos": adx_slope_pos,
        "ret_1w": ret_1w,
        "ret_5d": ret_5d,
        "ret_1m": ret_1m,
        "ret_3m": ret_3m,
        "ret_6m": ret_6m,
        "ret_12_1m": ret_12_1m,
        "breadth_pct_50dma": breadth_pct_50dma,
        "nifty_regime": nifty_regime,
        "mansfield_rs_52": mansfield_rs_52,
        "asm_gsm_flags": asm_gsm_flags,
        "upper_circuit_hits_60d": upper_circuit_hits_60d,
        "score": score,
        "score_full": score_full,
        "score_basic": score_basic,
        "score_basic_normalized": score_basic_normalized,
        "score_source": score_source,
        "data_gaps": data_gaps,
        "stale": stale,
        "rules_version": "2025-10-12A",
        "score_scale": "0-100",
        "badges": badges,
        "recommendation": recommendation,
        "reason": reason,
        "as_of": as_of_iso,
        "run_id": run_id,
        "score_band": score_bundle.band,
        "reason_codes": reason_codes,
        "score_breakdown": score_breakdown,
        "score_penalties": penalties_map,
        "score_components_raw": {
            "base": round(components.total_base(), 2),
            "with_context": round(components.total_with_context(), 2),
        },
    }

    row.setdefault("rsi", row.get("rsi14"))
    row.setdefault("adx", row.get("adx14"))
    row.setdefault("pct_from_52w_high", row.get("proximity_52w_high_pct"))
    row.setdefault("atr_pct", row.get("atr14_pct"))
    row.setdefault("pct_today", row.get("change_pct"))

    try:
        row["pre_gates_pass"] = global_pre_gates({**row, "close": row.get("last")})
    except Exception:
        row["pre_gates_pass"] = False

    if row.get("liquidity") is None:
        try:
            ser_liq = (df["close"] * df["volume"]).rolling(20, min_periods=5).mean()
            row["liquidity"] = float(ser_liq.iloc[-1]) if ser_liq.notna().any() else None
        except Exception:
            row["liquidity"] = None

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

    if not row.get("strength"):
        adx_val = row.get("adx")
        if isinstance(adx_val, (int, float)):
            row["strength"] = "High" if adx_val >= 35 else ("Medium" if adx_val >= 20 else "Low")

    if row.get("buy") is None and isinstance(row.get("score"), (int, float)):
        row["buy"] = "Yes" if row["score"] >= 75 else "No"

    badges_in: List[Any] = row.get("badges") or []
    has_action = any(isinstance(b, dict) and b.get("category") == "ACTION" for b in badges_in)
    if not has_action and isinstance(row.get("score"), (int, float)):
        badges_in.append(
            {"category": "ACTION", "label": "Buy"} if row["score"] >= 75 else {"category": "ACTION", "label": "Watch"}
        )

    cls_categories = {"BREAKOUT", "MOMENTUM", "WATCH", "IGNORE"}

    def _code_to_category(code: str) -> Optional[str]:
        c = (code or "").upper()
        if "BREAKOUT" in c:
            return "BREAKOUT"
        if "MOMENTUM" in c:
            return "MOMENTUM"
        if "WATCH" in c:
            return "WATCH"
        if "IGNORE" in c:
            return "IGNORE"
        return None

    has_classification = any(
        isinstance(b, dict) and str(b.get("category", "")).upper() in cls_categories for b in badges_in
    )
    if not has_classification:
        if row["score"] is not None and row["score"] >= 85 and (rsi14 or 0) >= 60 and (adx14 or 0) >= 30 and (pivot_clear_pct or 0) >= 2.0:
            badges_in.append({"category": "BREAKOUT", "label": "Very High Breakout"})
        elif row["score"] is not None and row["score"] >= 75:
            badges_in.append({"category": "MOMENTUM", "label": "High Momentum"})
        else:
            badges_in.append({"category": "WATCH", "label": "Watch"})

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

    intraday_date_override: Optional[str] = None
    if not as_of_date:
        override_raw = payload.get("intraday_trading_date")
        intraday_date_override = _as_of_date_str(override_raw)

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
                #log.warning("no prices for symbol; skipping row", extra={"symbol": sym, "as_of": as_of_iso})
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
                # Detect immutable/no-op writer (from datasets) to avoid misleading logs/paths
                is_noop_daily = getattr(w_daily, "_closed", False) and not hasattr(w_daily, "tmp_dir")
                if is_noop_daily:
                    # Skip writing; point snapshot_path to existing committed run or the as_of dir
                    existing_rid = _find_committed_run_for_as_of(as_of_date)
                    if existing_rid:
                        snapshot_path = str((
                            datasets.get_parquet_root() / "scores" / "daily" / f"as_of={as_of_date}" / f"run_id={existing_rid}"
                        ).resolve())
                    else:
                        snapshot_path = str((
                            datasets.get_parquet_root() / "scores" / "daily" / f"as_of={as_of_date}"
                        ).resolve())
                    log.info(
                        "scores_daily_skip_immutable",
                        extra={"as_of": as_of_date, "existing_run_id": existing_rid, "snapshot_path": snapshot_path}
                    )
                else:
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
                intraday_date_str = intraday_date_override or _utcnow_aware().date().strftime("%Y-%m-%d")
                target = (root / "scores" / f"intraday" / f"date={intraday_date_str}" / f"run_id={job.run_id}") if root else None
                log.info(
                    "scores_intraday_precommit",
                    extra={
                        "date": intraday_date_str,
                        "run_id": job.run_id,
                        "rows": rows_written,
                        "target": str(target) if target else None,
                        "date_override": bool(intraday_date_override),
                    }
                )
                w_intra = datasets.begin_atomic_write_scores_intraday(intraday_date_str, job.run_id)
                w_intra.write_df(pa.Table.from_pylist(rows))
                w_intra.commit()
                snapshot_path = str(
                    (datasets.get_parquet_root()
                     / "scores" / "intraday"
                     / f"date={intraday_date_str}"
                     / f"run_id={job.run_id}").resolve()
                )
                # post-commit quick listing
                try:
                    tgt = (datasets.get_parquet_root() / "scores" / "intraday" / f"date={intraday_date_str}" / f"run_id={job.run_id}")
                    files = [p.name for p in tgt.glob("*.parquet")] if tgt.exists() else []
                    log.info("scores_intraday_postcommit", extra={"target": str(tgt), "files": files})
                except Exception:
                    pass
                log.info("scores intraday written", extra={"date": intraday_date_str, "run_id": job.run_id, "rows": rows_written})
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
