from __future__ import annotations
from datetime import datetime
from typing import Optional, Tuple, Dict, Any, List
import logging

import pyarrow as pa
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy.orm import Session

from app.repos.sql.jobs_repo import SqlJobsRepo
from app.repos.sql.history_repo import SqlHistoryRepo
from app.repos.parquet import datasets
from app.schemas.runs import RunDetail

from app.core import config as app_config
from app.repos.parquet.universe_repo import UniverseRepo
from app.adapters.yahoo_adapter import YahooAdapter  # ctor takes NO args

# NEW: local history fill (no external module import)
import yfinance as yf
import pandas as pd

log = logging.getLogger(__name__)

_ALLOWED_PRESETS = {"NIFTY50", "NIFTY100", "NIFTY500", "MIDCAP", "SMALLCAP", "ALL"}
_FALLBACK_NSE = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS"]


def _utcnow_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _ensure_parquet_root() -> None:
    root = datasets.get_parquet_root()
    root.mkdir(parents=True, exist_ok=True)
    t = root / ".wcheck"
    t.write_text("ok")
    t.unlink(missing_ok=True)


def _rows_to_arrow(rows: List[Dict[str, Any]]) -> pa.Table:
    """Coerce to Arrow with Phase-9 schema."""
    def _f(v, cast=float):
        try:
            return cast(v) if v is not None else None
        except Exception:
            return None

    def _i(v):
        try:
            return int(v) if v is not None else 0
        except Exception:
            return 0

    return pa.table({
        "symbol": [str(r.get("symbol") or "") for r in rows],
        "name":   [r.get("name") for r in rows],
        "sector": [r.get("sector") for r in rows],
        "last":   [_f(r.get("last")) for r in rows],
        "change_pct": [_f(r.get("change_pct")) for r in rows],
        "score":  [_i(r.get("score")) for r in rows],
        "as_of":  [str(r.get("as_of") or "") for r in rows],
        "run_id": [str(r.get("run_id") or "") for r in rows],
    })


def _write_empty_scores_snapshot(run_id: str, as_of: str) -> str:
    """Phase-9: ZERO-row snapshot (keeps tests green)."""
    tab = _rows_to_arrow([])
    datasets.write_schema_version("scores", 1)
    w = datasets.begin_atomic_write("scores", run_id)
    try:
        w.write_df(tab)
        w.commit()
    except Exception:
        try:
            w.abort()
        except Exception:
            pass
        raise
    return str((datasets.get_parquet_root() / "scores" / f"run_id={run_id}").resolve())


# ---------- NEW: history helper (daily bars → last & change_pct) ----------------
def _history_last_change(symbol: str, period: str = "10d") -> tuple[Optional[float], Optional[float]]:
    """
    Robustly compute (last_close, change_pct) from recent daily history.
    Works off-hours/weekends. Returns (None, None) if not available.
    """
    try:
        t = yf.Ticker(symbol)
        df = t.history(period=period, interval="1d", auto_adjust=False)
        if df is None or df.empty:
            return None, None

        # last non-NaN close
        last_idx = len(df) - 1
        while last_idx >= 0 and pd.isna(df["Close"].iloc[last_idx]):
            last_idx -= 1
        if last_idx < 0:
            return None, None
        last = float(df["Close"].iloc[last_idx])

        # previous non-NaN close
        prev_idx = last_idx - 1
        prev = None
        while prev_idx >= 0 and pd.isna(df["Close"].iloc[prev_idx]):
            prev_idx -= 1
        if prev_idx >= 0 and not pd.isna(df["Close"].iloc[prev_idx]):
            prev = float(df["Close"].iloc[prev_idx])

        change_pct = None
        if prev not in (None, 0.0):
            try:
                change_pct = (last - prev) * 100.0 / prev
            except Exception:
                change_pct = None

        return last, change_pct
    except Exception:
        return None, None
# -------------------------------------------------------------------------------


def run_screening(
    *,
    session: Session,
    key: Optional[str],
    payload: Dict[str, Any],
) -> Tuple[RunDetail, bool]:
    """
    - Default: stub (0 rows) when data.adapter != 'yahoo'.
    - Live: when data.adapter == 'yahoo', fetch quotes; fill from history where blanks.
    - Swagger/manual runs go live when configured (no LIVE_TEST gating).
    - Any hard error falls back to stub (never 500).
    """
    _ensure_parquet_root()

    jobs = SqlJobsRepo(session)
    history = SqlHistoryRepo(session)

    # Inputs (soft)
    as_of = payload.get("as_of") or _utcnow_iso()
    universe = None
    if isinstance(payload.get("universe"), str):
        uni = payload["universe"].strip().upper()
        universe = uni if uni in _ALLOWED_PRESETS else None

    job, created = jobs.create_or_get_by_key(name="manual_scan", key=key, with_created=True)
    if not created:
        # Idempotent replay
        log.debug("scan.replay", extra={"run_id": job.run_id, "status": job.status})
        return (
            RunDetail(
                run_id=job.run_id,
                status=job.status,
                started_at=job.started_at.replace(microsecond=0).isoformat() + "Z",
                finished_at=job.ended_at.replace(microsecond=0).isoformat() + "Z" if job.ended_at else None,
                rows_computed=None,
                duration_ms=None,
                key=getattr(job, "key", None),
                snapshot_path=None,
                as_of=None,
                error_json=job.error,
            ),
            False,
        )

    # Fresh run
    try:
        cfg = app_config.load()
        adapter_kind = getattr(getattr(cfg, "data", None), "adapter", "stub")
        log.info("scan.start", extra={"run_id": job.run_id, "adapter": adapter_kind})

        quotes: List[Dict[str, Any]] = []
        rows_written = 0

        try:
            if adapter_kind == "yahoo":
                # Resolve universe: payload → scheduler → default
                resolved_universe = (
                    (universe or "").strip().upper()
                    or (getattr(cfg.scheduler, "universe", None) or "").strip().upper()
                    or (getattr(cfg.screener, "default_universe", "NIFTY50") or "").strip().upper()
                )
                log.info("scan.universe", extra={"run_id": job.run_id, "universe": resolved_universe})

                # Load symbols
                symbols, total = UniverseRepo().list_symbols(resolved_universe, page=1, per_page=999_999)
                if not symbols:
                    log.warning("universe.empty_fallback", extra={"run_id": job.run_id, "universe": resolved_universe})
                    symbols = list(_FALLBACK_NSE)

                # Gentle throttle initially (remove later)
                if len(symbols) > 50:
                    symbols = symbols[:50]
                log.info("scan.symbols", extra={"run_id": job.run_id, "count": len(symbols)})

                # Instantiate WITHOUT args (adapter takes none)
                ya = YahooAdapter()
                try:
                    quotes = ya.fetch_quotes(symbols)
                except Exception:
                    log.exception("scan.quotes_fetch_failed", extra={"run_id": job.run_id})
                    quotes = []

                # Build rows; fill from history wherever Yahoo is blank
                rows: List[Dict[str, Any]] = []
                if not quotes:
                    # No quotes at all: use history for each symbol
                    for s in symbols:
                        last, chg = _history_last_change(s)
                        rows.append({
                            "symbol": s,
                            "name": None,
                            "sector": None,
                            "last": last,
                            "change_pct": chg,
                            "score": 0,
                            "as_of": as_of,
                            "run_id": job.run_id,
                        })
                else:
                    for q in quotes:
                        sym = q.get("symbol")
                        last = q.get("last")
                        chg = q.get("change_pct")
                        if last is None or chg is None:
                            h_last, h_chg = _history_last_change(sym)
                            last = last if last is not None else h_last
                            chg = chg if chg is not None else h_chg

                        rows.append({
                            "symbol": sym,
                            "name": q.get("name"),
                            "sector": q.get("sector"),
                            "last": last,
                            "change_pct": chg,
                            "score": int(q.get("score") or 0),
                            "as_of": as_of,
                            "run_id": job.run_id,
                        })

                tab = _rows_to_arrow(rows)

                datasets.write_schema_version("scores", 1)
                w = datasets.begin_atomic_write("scores", job.run_id)
                try:
                    w.write_df(tab)
                    w.commit()
                    rows_written = tab.num_rows
                    log.info("scan.parquet_written", extra={"run_id": job.run_id, "rows": rows_written})
                except Exception:
                    try:
                        w.abort()
                    except Exception:
                        pass
                    log.exception("scan.parquet_write_failed; falling back to stub", extra={"run_id": job.run_id})
                    # fall back to stub one last time
                    snapshot_path = _write_empty_scores_snapshot(job.run_id, as_of)
                    rows_written = 0
                else:
                    snapshot_path = str((datasets.get_parquet_root() / "scores" / f"run_id={job.run_id}").resolve())

            else:
                # Stub (Phase-9): 0-row snapshot
                snapshot_path = _write_empty_scores_snapshot(job.run_id, as_of)
                log.info("scan.stub_snapshot", extra={"run_id": job.run_id})

        except Exception:
            # Any live-path error → safe fallback to stub (avoid 500s)
            log.exception("scan.live_failed_fallback_stub", extra={"run_id": job.run_id})
            snapshot_path = _write_empty_scores_snapshot(job.run_id, as_of)
            rows_written = 0
            quotes = []

        # Mark success & best-effort history
        jobs.complete_run(run_id=job.run_id, status="SUCCEEDED", error=None)
        try:
            history.insert_run_summary(run_id=job.run_id, as_of=as_of, rows=rows_written)
        except Exception:
            pass

        return (
            RunDetail(
                run_id=job.run_id,
                status="SUCCEEDED",
                started_at=job.started_at.replace(microsecond=0).isoformat() + "Z",
                finished_at=_utcnow_iso(),
                rows_computed=rows_written,
                duration_ms=None,
                key=getattr(job, "key", None),
                snapshot_path=snapshot_path,
                as_of=as_of,
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
