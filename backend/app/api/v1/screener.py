# backend/app/api/v1/screener.py
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from app.schemas.screener import (
    ScreenerList,
    ScreenerRow,
    TopMoverEntry,
    TopMovers,
    ScreenerRunDate,
    ScreenerRunDateList,
    ScreenerRunSummary,
    ScreenerRunList,
)
from app.schemas.generated.models import DrawerNextAction
from app.repos.parquet.scores_repo import ScoresRepo
from app.services.detail_service import DetailDeps, build_drawer_detail
from app.repos.market_data_repo import MarketDataRepo
from app.repos.parquet import datasets


try:
    from app.repos.sql.positions_repo import PositionsRepo
except Exception:  # pragma: no cover
    PositionsRepo = None  # type: ignore

try:
    from app.repos.sql.snapshot_pins_repo import SnapshotPinsRepo
except Exception:  # pragma: no cover
    SnapshotPinsRepo = None  # type: ignore

# ADDED: minimal imports to clean NaN/Inf payloads and log drops
import math
import numbers
import logging
import csv
import io
import json
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from app.core import config as app_config
from app.repos.parquet.universe_repo import UniverseRepo, PRESETS as UNIVERSE_PRESETS

router = APIRouter(tags=["Screener"])
repo = ScoresRepo()
log = logging.getLogger(__name__)

RUN_MODE_INTRADAY = "intraday"
RUN_MODE_EOD = "eod"
RUN_MODE_SET = {RUN_MODE_INTRADAY, RUN_MODE_EOD}
try:
    _IST_TZ = ZoneInfo("Asia/Kolkata")
except Exception:  # pragma: no cover - fallback when tzdata missing
    _IST_TZ = None

SCREENER_REPO_COLUMNS = [
    # Core quote & identity
    "symbol",
    "name",
    "sector",
    "last",
    "close",
    "price",
    "change_pct",
    # Score & strength
    "score",
    "strength",
    # Indicators & returns
    "rsi",
    "adx",
    "ret_12_1m",
    "ret_6m",
    "ret_3m",
    "ret_1m",
    "pct_from_52w_high",
    "atr_pct",
    "liquidity",
    "vol_spike",
    "pct_today",
    # Decisioning
    "buy",
    "reason",
    # Meta
    "source",
    "stale",
    "badges",
    "run_id",
    "as_of",
    "last_index",
    # Legacy helper; if present we'll derive 1W fields
    "ret_1w",
    # If parquet already contains these, pass through
    "wk_change",
    "wk_change_pct",
]

PERIOD_FIELD_MAP: dict[str, str] = {
    "1d": "change_pct",
    "1w": "ret_1w",
    "1m": "ret_1m",
    "3m": "ret_3m",
}
TOP_LIMIT = 5
FETCH_MULTIPLIER = 5
TOP_COLUMNS = [
    "symbol",
    "name",
    "sector",
    "last",
    "change_pct",
    "wk_change_pct",
    "ret_1w",
    "ret_1m",
    "ret_3m",
    "score",
    "run_id",
    "as_of",
]

def _format_date_label(date_str: str) -> str:
    try:
        parsed = datetime.strptime(date_str, "%Y-%m-%d").date()
        return parsed.strftime("%a %d %b")
    except Exception:
        return date_str


def _run_id_to_datetime(run_id: Optional[str]) -> Optional[datetime]:
    if not run_id:
        return None
    try:
        return datetime.strptime(run_id, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _format_intraday_label(run_id: str) -> str:
    dt = _run_id_to_datetime(run_id)
    if dt is None:
        return run_id
    if _IST_TZ is not None:
        local_dt = dt.astimezone(_IST_TZ)
        return local_dt.strftime("%I:%M %p IST").lstrip("0")
    return dt.strftime("%H:%M UTC")


def _format_eod_label(as_of: str) -> str:
    base = _format_date_label(as_of)
    return f"{base} EOD"


def _today_ist_str() -> str:
    if _IST_TZ is None:
        return datetime.now(timezone.utc).date().strftime("%Y-%m-%d")
    return datetime.now(_IST_TZ).date().strftime("%Y-%m-%d")


def _list_intraday_dates(limit: int) -> List[ScreenerRunDate]:
    try:
        root = datasets.get_parquet_root() / "scores" / "intraday"
    except Exception:
        return []
    if not root.exists():
        return []

    out: List[ScreenerRunDate] = []
    for date_dir in sorted(
        (p for p in root.glob("date=*") if p.is_dir()),
        key=lambda p: p.name.split("=", 1)[-1],
        reverse=True,
    ):
        date_str = date_dir.name.split("=", 1)[-1]
        try:
            run_ids = datasets.list_intraday_runs(date_str)
        except Exception:
            run_ids = []
        run_count = len(run_ids)
        if run_count == 0:
            continue
        out.append(
            ScreenerRunDate(
                mode=RUN_MODE_INTRADAY,
                trade_date=date_str,
                run_count=run_count,
                label=_format_date_label(date_str),
            )
        )
        if len(out) >= limit:
            break
    return out


def _list_eod_run_ids(as_of: str) -> List[Optional[str]]:
    try:
        root = datasets.get_parquet_root() / "scores" / "daily" / f"as_of={as_of}"
    except Exception:
        return []
    if not root.exists():
        return []

    run_ids: List[Optional[str]] = []
    for run_dir in root.glob("run_id=*"):
        if not run_dir.is_dir():
            continue
        rid = run_dir.name.split("run_id=", 1)[-1]
        if rid and (run_dir / "_SUCCESS").exists():
            run_ids.append(rid)
    if run_ids:
        return sorted(run_ids, reverse=True)

    # Handle legacy layout (parquet parts directly under as_of)
    success_marker = (root / "_SUCCESS").exists()
    parquet_files = any(p.suffix == ".parquet" for p in root.glob("*.parquet"))
    if success_marker or parquet_files:
        return [None]
    return []


def _list_eod_dates(limit: int) -> List[ScreenerRunDate]:
    try:
        root = datasets.get_parquet_root() / "scores" / "daily"
    except Exception:
        return []
    if not root.exists():
        return []

    out: List[ScreenerRunDate] = []
    for date_dir in sorted(
        (p for p in root.glob("as_of=*") if p.is_dir()),
        key=lambda p: p.name.split("=", 1)[-1],
        reverse=True,
    ):
        as_of = date_dir.name.split("=", 1)[-1]
        run_ids = _list_eod_run_ids(as_of)
        run_count = len(run_ids)
        if run_count == 0:
            continue
        out.append(
            ScreenerRunDate(
                mode=RUN_MODE_EOD,
                as_of=as_of,
                run_count=run_count,
                label=_format_date_label(as_of),
            )
        )
        if len(out) >= limit:
            break
    return out


def _build_intraday_summary(trade_date: str, run_id: str) -> ScreenerRunSummary:
    dt = _run_id_to_datetime(run_id)
    return ScreenerRunSummary(
        mode=RUN_MODE_INTRADAY,
        run_id=run_id,
        trade_date=trade_date,
        started_at=dt,
        completed_at=None,
        label=_format_intraday_label(run_id),
    )


def _build_eod_summary(as_of: str, run_id: Optional[str]) -> ScreenerRunSummary:
    dt = _run_id_to_datetime(run_id)
    return ScreenerRunSummary(
        mode=RUN_MODE_EOD,
        run_id=run_id,
        as_of=as_of,
        trade_date=None,
        started_at=dt,
        completed_at=None,
        label=_format_eod_label(as_of),
    )


def _get_latest_snapshot_summary() -> ScreenerRunSummary:
    """
    Decide the single most recent snapshot with EOD > Intraday precedence.
    1) If today's EOD exists → return today's EOD (latest run if multiple).
    2) Else if today's intraday runs exist → return latest intraday run today.
    3) Else return latest available EOD (<= today).
    """
    today = _today_ist_str()

    # 1) Today’s EOD?
    eod_run_ids_today = _list_eod_run_ids(today)
    if eod_run_ids_today:
        rid = eod_run_ids_today[0]  # already sorted latest-first
        return _build_eod_summary(today, rid)

    # 2) Today’s intraday?
    try:
        intra_run_ids_today = datasets.list_intraday_runs(today)
    except Exception:
        intra_run_ids_today = []
    intra_run_ids_today = sorted(intra_run_ids_today, reverse=True)
    if intra_run_ids_today:
        return _build_intraday_summary(today, intra_run_ids_today[0])

    # 3) Fallback to latest EOD ≤ today
    eod_dates = _list_eod_dates(1)
    if eod_dates:
        as_of = eod_dates[0].as_of or today
        run_ids = _list_eod_run_ids(as_of)
        rid = run_ids[0] if run_ids else None
        return _build_eod_summary(as_of, rid)

    raise HTTPException(status_code=404, detail="No snapshots available")


@router.get("/screener/latest", response_model=ScreenerRunSummary)
def get_latest_snapshot() -> ScreenerRunSummary:
    """
    Return the single latest snapshot across modes with EOD > Intraday precedence.
    Use this in the UI to auto-select mode/date/run_id on initial load.
    """
    return _get_latest_snapshot_summary()


@router.get("/screener/run-dates", response_model=ScreenerRunDateList)
def get_screener_run_dates(
    mode: Literal["intraday", "eod"] = Query(
        RUN_MODE_INTRADAY, description="Snapshot category to inspect."
    ),
    limit: int = Query(
        30,
        ge=1,
        le=120,
        description="Maximum number of dates to return (most recent first).",
    ),
):
    if mode == RUN_MODE_INTRADAY:
        dates = _list_intraday_dates(limit)
    else:
        dates = _list_eod_dates(limit)
    latest = dates[0] if dates else None
    return ScreenerRunDateList(mode=mode, latest=latest, dates=dates)


@router.get("/screener/runs", response_model=ScreenerRunList)
def get_screener_runs(
    mode: Literal["intraday", "eod"] = Query(
        RUN_MODE_INTRADAY, description="Snapshot category to inspect."
    ),
    trade_date: Optional[str] = Query(
        None,
        description="Trading date (YYYY-MM-DD). Required when mode=intraday.",
    ),
    as_of: Optional[str] = Query(
        None,
        description="End-of-day snapshot date (YYYY-MM-DD). Required when mode=eod.",
    ),
    limit: int = Query(
        25,
        ge=1,
        le=200,
        description="Maximum number of runs to return (intraday only).",
    ),
):
    if mode == RUN_MODE_INTRADAY:
        target_date = trade_date
        if not target_date:
            latest_dates = _list_intraday_dates(1)
            target_date = latest_dates[0].trade_date if latest_dates else None
        if not target_date:
            return ScreenerRunList(mode=mode, trade_date=None, items=[], latest=None)
        try:
            run_ids = datasets.list_intraday_runs(target_date)
        except Exception:
            run_ids = []
        run_ids = sorted(run_ids, reverse=True)
        if limit and len(run_ids) > limit:
            run_ids = run_ids[:limit]
        summaries = [_build_intraday_summary(target_date, rid) for rid in run_ids]
        latest = summaries[0] if summaries else None
        return ScreenerRunList(
            mode=mode,
            trade_date=target_date,
            items=summaries,
            latest=latest,
        )

    target_as_of = as_of
    if not target_as_of:
        latest_dates = _list_eod_dates(1)
        target_as_of = latest_dates[0].as_of if latest_dates else None
    if not target_as_of:
        return ScreenerRunList(mode=mode, as_of=None, items=[], latest=None)

    run_ids = _list_eod_run_ids(target_as_of)
    summaries = [_build_eod_summary(target_as_of, rid) for rid in run_ids] if run_ids else []
    latest = summaries[0] if summaries else None
    return ScreenerRunList(
        mode=mode,
        as_of=target_as_of,
        items=summaries,
        latest=latest,
    )

_universe_repo: UniverseRepo | None = None



def _get_universe_repo() -> UniverseRepo:
    global _universe_repo
    if _universe_repo is None:
        _universe_repo = UniverseRepo()
    return _universe_repo


@lru_cache(maxsize=16)
def _load_universe_symbols(preset: str) -> tuple[str, ...]:
    repo = _get_universe_repo()
    symbols, _ = repo.list_symbols(preset, page=1, per_page=1_000_000)
    return tuple(symbols)

_detail_deps_cache: DetailDeps | None = None


def _get_detail_deps() -> DetailDeps:
    global _detail_deps_cache
    if _detail_deps_cache is None:
        try:
            positions_repo = PositionsRepo() if PositionsRepo else None
        except Exception:
            positions_repo = None
        try:
            snapshot_repo = SnapshotPinsRepo() if SnapshotPinsRepo else None
        except Exception:
            snapshot_repo = None
        try:
            indicators_repo = MarketDataRepo()
        except Exception:
            indicators_repo = None
        try:
            from app.core import db as core_db
            try:
                sessionmaker = core_db.get_sessionmaker()
            except Exception:
                core_db.init_sqlite()
                sessionmaker = core_db.get_sessionmaker()
        except Exception:
            sessionmaker = None
        _detail_deps_cache = DetailDeps(
            scores_repo=repo,
            indicators_repo=indicators_repo,
            positions_repo=positions_repo,
            snapshot_pins_repo=snapshot_repo,
            sessionmaker=sessionmaker,
        )
    return _detail_deps_cache


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_as_of(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return date.fromisoformat(str(value)[:10])
    except Exception:
        return None


def _fetch_sorted_rows(field: str, descending: bool) -> Tuple[list[tuple[dict[str, Any], float]], Optional[str], Optional[str]]:
    sort_dir = "desc" if descending else "asc"
    sort = f"{field}.{sort_dir},score.desc"
    per_page = max(TOP_LIMIT * FETCH_MULTIPLIER, 20)
    items, _total, resolved_run_id, resolved_as_of = repo.read(
        run_id=None,
        as_of_str=None,
        filters={},
        sort=sort,
        page=1,
        per_page=per_page,
        columns=TOP_COLUMNS,
    )
    rows: list[tuple[dict[str, Any], float]] = []
    for row in items or []:
        value = _to_float(row.get(field))
        if value is None:
            continue
        rows.append((row, value))
    rows.sort(key=lambda item: item[1], reverse=descending)
    return rows[:TOP_LIMIT], resolved_run_id, resolved_as_of


# Treat these query params as non-filter controls. Everything else maps into filter ops.
KNOWN_KEYS = {"run_id", "as_of", "sort", "page", "per_page", "universe", "symbol"}


def _ensure_tz_as_of(v, fallback_dt: datetime) -> datetime:
    # Accept datetime with/without tz, or strings like "YYYY-MM-DD" / ISO 8601
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, str):
        try:
            # "YYYY-MM-DDTHH:MM:SS±HH:MM" -> datetime (may already have tz)
            dt = datetime.fromisoformat(v)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            # "YYYY-MM-DD" -> midnight UTC
            try:
                d = datetime.strptime(v[:10], "%Y-%m-%d")
                return d.replace(tzinfo=timezone.utc)
            except Exception:
                return fallback_dt
    return fallback_dt


def _parse_filters(params) -> Dict[tuple[str, str], Any]:
    """
    Convert query params (k=v) into a normalized filter dict usable by the repo.

    Suffix operators supported:
      .in   → IN set (comma separated)
      .gte  → >=
      .gt   → >
      .lte  → <=
      .lt   → <
      .like → prefix-match if value endswith '%', else equality
      .eq   → equality

    Anything not listed in KNOWN_KEYS is treated as a potential filter.
    """
    out: Dict[tuple[str, str], Any] = {}
    for k, v in params.items():
        if k in KNOWN_KEYS:
            continue
        if k.endswith(".in"):
            out[(k[:-3], "in")] = [x.strip() for x in v.split(",") if x.strip()]
        elif k.endswith(".gte"):
            try:
                out[(k[:-4], "gte")] = float(v)
            except Exception:
                pass
        elif k.endswith(".gt"):
            try:
                out[(k[:-3], "gt")] = float(v)
            except Exception:
                pass
        elif k.endswith(".lte"):
            try:
                out[(k[:-4], "lte")] = float(v)
            except Exception:
                pass
        elif k.endswith(".lt"):
            try:
                out[(k[:-3], "lt")] = float(v)
            except Exception:
                pass
        elif k.endswith(".like"):
            out[(k[:-5], "like")] = v
        elif k.endswith(".eq"):
            out[(k[:-3], "eq")] = v
    return out


def _normalize_screener_rows(raw_items: List[Dict[str, Any]]) -> Tuple[List[ScreenerRow], int]:
    """Normalize parquet rows into ScreenerRow models."""
    norm_items: List[ScreenerRow] = []
    dropped = 0

    for r in raw_items:
        if r.get("last") is None:
            fallback_last = r.get("close") if r.get("close") is not None else r.get("price")
            if fallback_last is not None:
                r["last"] = fallback_last

        s_val = r.get("score")
        if isinstance(s_val, float) and 0.0 <= s_val <= 1.0:
            s_val = s_val * 100.0
        if not _is_num(r.get("last")) or not _is_num(s_val if s_val is not None else 0):
            dropped += 1
            continue
        r["score"] = int(round(float(s_val))) if s_val is not None else 0

        _derive_week_fields(r)

        badges = r.get("badges") or []
        norm_badges: List[dict] = []
        allowed = {"BREAKOUT", "MOMENTUM", "WATCH", "IGNORE"}
        badge_remap = {
            "BAND": "MOMENTUM",
            "PRICE": "MOMENTUM",
            "VOLUME": "MOMENTUM",
            "TREND": "MOMENTUM",
            "INFO": "WATCH",
            "DATA": "WATCH",
        }

        for b in badges:
            if isinstance(b, dict) and "category" in b and "label" in b:
                cat = str(b["category"]).strip().upper()
                cat = badge_remap.get(cat, cat)
                if cat not in allowed:
                    cat = "WATCH"
                norm_badges.append({"category": cat, "label": str(b["label"])})
            elif isinstance(b, dict):
                norm_badges.append(_badge_to_contract_shape(b))
            elif isinstance(b, str):
                norm_badges.append({"category": "WATCH", "label": b})

        for b in norm_badges:
            b["category"] = str(b["category"]).strip().upper()
            if b["category"] not in allowed:
                log.error(
                    "screener: badge normalization failed",
                    extra={"raw": badges, "normalized": norm_badges},
                )
                b["category"] = "WATCH"

        r["badges"] = norm_badges
        r.pop("ret_1w", None)

        _clean_nonfinite_inplace(r)

        if r.get("change_pct") is None:
            r["change_pct"] = 0.0

        norm_items.append(ScreenerRow(**r))

    return norm_items, dropped


def _collect_screener_rows(
    *,
    run_id: Optional[str],
    as_of: Optional[str],
    sort: str = "score.desc,last.desc",
    chunk_size: int = 500,
) -> Tuple[List[ScreenerRow], Optional[str], Optional[str], int]:
    """
    Retrieve the full screener snapshot for export by paging through repo.read.
    Returns (rows, resolved_run_id, resolved_as_of, total_rows).
    """
    page = 1
    aggregated: List[ScreenerRow] = []
    resolved_run_id: Optional[str] = None
    resolved_as_of: Optional[str] = None
    total_rows: int = 0
    dropped_total = 0

    while True:
        try:
            items, total, rid, as_of_val = repo.read(
                run_id=run_id,
                as_of_str=as_of,
                filters={},
                sort=sort,
                page=page,
                per_page=chunk_size,
                columns=SCREENER_REPO_COLUMNS,
            )
        except Exception as exc:
            log.exception("screener_export: repo.read failed", extra={"run_id": run_id, "as_of": as_of, "page": page})
            raise HTTPException(status_code=500, detail="Failed to load screener snapshot") from exc

        norm_items, dropped = _normalize_screener_rows(items)
        aggregated.extend(norm_items)
        dropped_total += dropped

        if resolved_run_id is None and rid:
            resolved_run_id = rid
        if resolved_as_of is None and as_of_val:
            resolved_as_of = as_of_val

        total_rows = total or len(aggregated)

        if len(items) < chunk_size or len(aggregated) >= total_rows:
            break
        page += 1

    if dropped_total:
        log.warning("screener_export: dropped invalid rows", extra={"dropped": dropped_total})

    return aggregated, resolved_run_id, resolved_as_of, total_rows


def _prepare_row_for_csv(row: ScreenerRow) -> Dict[str, Any]:
    data = row.model_dump(mode="json")
    prepared: Dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, (dict, list)):
            prepared[key] = json.dumps(value, ensure_ascii=False)
        else:
            prepared[key] = value
    return prepared


def _rows_to_csv(rows: List[ScreenerRow]) -> str:
    if not rows:
        return ""
    prepared = [_prepare_row_for_csv(r) for r in rows]
    fieldnames: List[str] = []
    seen: set[str] = set()
    for row in prepared:
        for key in row.keys():
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in prepared:
        writer.writerow(row)
    return buffer.getvalue()


def _badge_category_from_code_or_text(code: str, text: str) -> str:
    """
    Map legacy badge 'code'/'text' to contract categories: BREAKOUT | MOMENTUM | WATCH | IGNORE.
    Keep it minimal & deterministic.
    """
    c = (code or "").upper()
    t = (text or "").upper()
    # Code-driven mapping (preferred)
    if "BREAKOUT" in c:
        return "BREAKOUT"
    if "MOMENTUM" in c or "HIGH_MOMENTUM" in c:
        return "MOMENTUM"
    if "WATCH" in c:
        return "WATCH"
    if "IGNORE" in c:
        return "IGNORE"
    # Fallback: text keywords
    if "BREAKOUT" in t:
        return "BREAKOUT"
    if "MOMENTUM" in t or "TREND" in t:
        return "MOMENTUM"
    if "WATCH" in t:
        return "WATCH"
    if "IGNORE" in t or "AVOID" in t:
        return "IGNORE"
    # Safe default
    return "WATCH"


def _badge_to_contract_shape(b: dict) -> dict:
    """
    Normalize a legacy badge dict into contract Badge shape:
      { category: Literal['BREAKOUT','MOMENTUM','WATCH','IGNORE'], label: str }
    """
    code = (b.get("code") or b.get("key") or "")  # legacy inputs
    label = (b.get("label") or b.get("text") or code or "").strip() or "Badge"
    category = _badge_category_from_code_or_text(code, label)
    return {"category": category, "label": label}


def _derive_week_fields(row: Dict[str, Any]) -> None:
    """Ensure wk_change and wk_change_pct exist (derive from ret_1w if needed)."""
    if row.get("wk_change") is not None and row.get("wk_change_pct") is not None:
        return
    last = row.get("last")
    ret_1w = row.get("ret_1w")  # legacy helper if present
    if last is None or ret_1w is None:
        row.setdefault("wk_change", None)
        row.setdefault("wk_change_pct", None)
        return
    try:
        r = float(ret_1w)
        denom = 1.0 + (r / 100.0)
        if denom <= 0.0:
            row["wk_change"] = None
            row["wk_change_pct"] = None
            return
        base = float(last) / denom
        row["wk_change"] = float(last) - base
        row["wk_change_pct"] = r
    except Exception:
        row["wk_change"] = None
        row["wk_change_pct"] = None


# ADDED: minimal cleaner so JSONResponse won't 500 on NaN/Inf
def _clean_nonfinite_inplace(d: Dict[str, Any]) -> None:
    for k, v in list(d.items()):
        if isinstance(v, numbers.Real):
            x = float(v)
            if not math.isfinite(x):
                d[k] = None
        elif isinstance(v, list):
            cleaned = []
            for x in v:
                if isinstance(x, numbers.Real):
                    xf = float(x)
                    cleaned.append(xf if math.isfinite(xf) else None)
                else:
                    cleaned.append(x)
            d[k] = cleaned
        # nested dicts left as-is


def _is_num(v: Any) -> bool:
    return isinstance(v, numbers.Real) and math.isfinite(float(v))


@router.get("/screener/top-movers", response_model=TopMovers)
def get_top_movers(period: str = Query("1d", description="Period for percent change", pattern="^(1d|1w|1m|3m)$")) -> TopMovers:
    field = PERIOD_FIELD_MAP.get(period)
    if field is None:
        raise HTTPException(status_code=400, detail={"code": "invalid_period", "detail": "Supported periods are 1d, 1w, 1m, 3m."})

    gain_rows, run_id_gainers, as_of_gainers = _fetch_sorted_rows(field, True)
    lose_rows, run_id_losers, as_of_losers = _fetch_sorted_rows(field, False)

    detail_deps = _get_detail_deps()
    detail_cache: dict[tuple[str, Optional[str]], DrawerNextAction] = {}

    def resolve_next_action(symbol: str, run_id_hint: Optional[str]) -> DrawerNextAction:
        key = (symbol, run_id_hint)
        if key not in detail_cache:
            try:
                detail = build_drawer_detail(symbol, run_id_hint, detail_deps)
                action_data = detail.get("next_action") if isinstance(detail, dict) else None
                if isinstance(action_data, DrawerNextAction):
                    action = action_data
                elif isinstance(action_data, dict):
                    action = DrawerNextAction.model_validate(action_data)
                else:
                    action = DrawerNextAction(code="WATCH", text="Watch (no detail)", reasons=[], refs={})
            except Exception:
                log.exception("top_movers: unable to build detail", extra={"symbol": symbol, "run_id": run_id_hint})
                action = DrawerNextAction(code="WATCH", text="Watch (detail unavailable)", reasons=[], refs={})
            detail_cache[key] = action
        return detail_cache[key]

    def make_entry(row: dict[str, Any], value: float) -> Optional[TopMoverEntry]:
        symbol = row.get("symbol")
        if not symbol:
            return None
        price = _to_float(row.get("last"))
        change = _to_float(value)
        if change is None:
            return None
        score_value = _to_float(row.get("score"))
        action = resolve_next_action(str(symbol), row.get("run_id"))
        return TopMoverEntry(
            symbol=str(symbol),
            name=row.get("name"),
            sector=row.get("sector"),
            price=price if price is not None else 0.0,
            change_pct=change,
            score=score_value,
            next_action=action,
        )

    gainers: list[TopMoverEntry] = []
    for row, value in gain_rows:
        entry = make_entry(row, value)
        if entry:
            gainers.append(entry)
        if len(gainers) >= TOP_LIMIT:
            break

    losers: list[TopMoverEntry] = []
    for row, value in lose_rows:
        entry = make_entry(row, value)
        if entry:
            losers.append(entry)
        if len(losers) >= TOP_LIMIT:
            break

    run_id = run_id_gainers or run_id_losers
    as_of_value = _parse_as_of(as_of_gainers) or _parse_as_of(as_of_losers)

    return TopMovers(
        period=period,
        generated_at=datetime.now(timezone.utc),
        run_id=run_id,
        as_of=as_of_value,
        gainers=gainers,
        losers=losers,
    )


@router.get("/screener", response_model=ScreenerList)
def list_screener(
    request: Request,
    run_id: Optional[str] = Query(None, description="Exact snapshot run id, e.g. 20250912T093000Z"),
    as_of: Optional[str] = Query(None, description="YYYY-MM-DD; pick last run on/before this date"),
    sort: str = Query("score.desc,last.desc", description="Comma list e.g. score.desc,last.desc"),
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=500),
    universe: Optional[str] = Query(None, description="Universe preset (e.g., NIFTY500, NIFTY50, ALL)"),
    symbol: Optional[str] = Query(None, description="Exact ticker symbol (e.g., SUMEETINDS.NS)"),
):
    # Parse filters from the raw query string
    params = dict(request.query_params)
    filters = _parse_filters(params)

    symbol_value = (symbol or '').strip()
    if symbol_value:
        filters[("symbol", "eq")] = symbol_value.upper()

    resolved_universe = (universe or "").strip().upper()
    if not resolved_universe:
        try:
            cfg = app_config.load()
            default_uni = getattr(getattr(cfg, 'screener', None), 'default_universe', None)
        except Exception:
            default_uni = None
        resolved_universe = (default_uni or "").strip().upper()

    if resolved_universe and resolved_universe not in UNIVERSE_PRESETS:
        raise HTTPException(status_code=400, detail=f"Unknown universe preset '{resolved_universe}'")

    if resolved_universe and resolved_universe != 'ALL':
        try:
            universe_symbols = list(_load_universe_symbols(resolved_universe))
        except Exception as exc:
            log.exception('screener: failed to load universe preset', extra={'universe': resolved_universe})
            raise HTTPException(status_code=500, detail='Failed to load universe preset') from exc

        sym_key = ('symbol', 'in')
        if sym_key in filters:
            existing_raw = filters.get(sym_key) or []
            if isinstance(existing_raw, (list, tuple, set)):
                existing_list = list(existing_raw)
            else:
                existing_list = [existing_raw]
            universe_set = set(universe_symbols)
            filters[sym_key] = [s for s in existing_list if s in universe_set]
        else:
            filters[sym_key] = list(universe_symbols)

    try:
        items, total, resolved_run_id, resolved_as_of = repo.read(
            run_id=run_id,
            as_of_str=as_of,
            filters=filters,
            sort=sort,
            page=page,
            per_page=per_page,
            columns=SCREENER_REPO_COLUMNS,
        )
    except Exception:
        items, total, resolved_run_id, resolved_as_of = [], 0, None, None

    norm_items, dropped = _normalize_screener_rows(items)
    if dropped:
        log.warning(
            "screener: dropped invalid rows (missing last/score)",
            extra={"dropped": dropped},
        )

    # Ensure tz-aware as_of for response model
    as_of_dt = _ensure_tz_as_of(resolved_as_of, datetime.now(timezone.utc))

    return ScreenerList(
        items=norm_items,
        pagination={"page": page, "per_page": per_page, "total": total, "next_cursor": None},
        as_of=as_of_dt,
        run_id=resolved_run_id,
    )


@router.get("/screener/export")
def export_screener(
    format: str = Query("csv", pattern="^(csv|json)$"),
    run_id: str | None = Query(None),
    as_of: str | None = Query(None),
):
    """
    Export the full screener snapshot (no pagination).
    - Intraday: provide run_id
    - EOD:      provide as_of=YYYY-MM-DD
    """
    repo = ScoresRepo()

    # Read EVERYTHING: per_page is set huge so no slicing occurs inside repo.read()
    rows, total, rid_used, resolved_as_of = repo.read(
        run_id=run_id,
        as_of_str=as_of,
        filters={},          # export is unfiltered (by design)
        sort="",             # keep on-disk order unless client later wants a specific sort
        page=1,
        per_page=10**9,      # <— key change: effectively "all rows"
        columns=None,        # full projection
    )

    # Filename
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    if run_id:
        fname_base = f"screener_intraday_{run_id}"
    else:
        fname_base = f"screener_eod_{resolved_as_of or as_of or 'latest'}"
    if format == "json":
        fname = f"{fname_base}_{ts}.json"
    else:
        fname = f"{fname_base}_{ts}.csv"

    # Empty data guard: still return a valid file with header (or empty JSON array)
    if format == "json":
        payload = json.dumps(rows, ensure_ascii=False)
        return Response(
            content=payload,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{fname}"'},
        )

    # CSV export (all rows)
    fieldnames = sorted({k for r in rows for k in r.keys()}) if rows else []
    buf = io.StringIO()
    if fieldnames:
        writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            # ensure all keys present
            writer.writerow({k: r.get(k, "") for k in fieldnames})
    else:
        # no data: write minimal empty CSV
        buf.write("")

    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
