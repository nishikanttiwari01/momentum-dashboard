# backend/app/api/v1/screener.py
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query, Request
from app.schemas.screener import ScreenerList, ScreenerRow, TopMoverEntry, TopMovers
from app.schemas.generated.models import DrawerNextAction
from app.repos.parquet.scores_repo import ScoresRepo
from app.services.detail_service import DetailDeps, build_drawer_detail
from app.repos.market_data_repo import MarketDataRepo


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
from datetime import date, datetime, timezone
from functools import lru_cache

from app.core import config as app_config
from app.repos.parquet.universe_repo import UniverseRepo, PRESETS as UNIVERSE_PRESETS

router = APIRouter(tags=["Screener"])
repo = ScoresRepo()
log = logging.getLogger(__name__)

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
        _detail_deps_cache = DetailDeps(
            scores_repo=repo,
            indicators_repo=indicators_repo,
            positions_repo=positions_repo,
            snapshot_pins_repo=snapshot_repo,
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
            columns=[
                # Core quote & identity
                "symbol", "name", "sector", "last", "close", "price", "change_pct",
                # Score & strength
                "score", "strength",
                # Indicators & returns
                "rsi", "adx", "ret_12_1m", "ret_6m", "ret_3m", "ret_1m",
                "pct_from_52w_high", "atr_pct", "liquidity", "vol_spike", "pct_today",
                # Decisioning
                "buy", "reason",
                # Meta
                "source", "stale", "badges",
                "run_id", "as_of", "last_index",
                # Legacy helper; if present we’ll derive 1W fields
                "ret_1w",
                # If parquet already contains these, we’ll pass them through
                "wk_change", "wk_change_pct",
            ],
        )
    except Exception:
        items, total, resolved_run_id, resolved_as_of = [], 0, None, None

    # Normalize each row into the contract-safe shape
    norm_items: List[ScreenerRow] = []
    dropped = 0

    for r in items:
        # Fill last from close/price if missing
        if r.get("last") is None:
            fallback_last = r.get("close")
            if fallback_last is None:
                fallback_last = r.get("price")
            if fallback_last is not None:
                r["last"] = fallback_last

        # Ensure 'last' and 'score' are valid; drop otherwise (prevents 500s)
        s_val = r.get("score")
        if isinstance(s_val, float) and 0.0 <= s_val <= 1.0:
            s_val = s_val * 100.0  # normalize if score stored in 0..1
        if not _is_num(r.get("last")) or not _is_num(s_val if s_val is not None else 0):
            dropped += 1
            continue

        # Keep normalized 0..100 integer score
        r["score"] = int(round(float(s_val))) if s_val is not None else 0

        _derive_week_fields(r)

        # Normalize badges → contract shape {category,label}
        badges = r.get("badges") or []
        norm_badges: List[dict] = []
        allowed_categories = {"BREAKOUT", "MOMENTUM", "WATCH", "IGNORE", "ACTION"}
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
                if cat not in allowed_categories:
                    cat = "WATCH"
                norm_badges.append({"category": cat, "label": str(b["label"])})
            elif isinstance(b, dict):
                norm_badges.append(_badge_to_contract_shape(b))
            elif isinstance(b, str):
                # extremely defensive: turn free-text into a WATCH badge
                norm_badges.append({"category": "WATCH", "label": b})
        for b in norm_badges:
            b["category"] = str(b["category"]).strip().upper()
            if b["category"] not in allowed_categories:
                log.error(
                    "screener: badge normalization failed",
                    extra={"raw": badges, "normalized": norm_badges},
                )
                b["category"] = "WATCH"
        r["badges"] = norm_badges
        # Clean up legacy helper
        r.pop("ret_1w", None)

        # Sanitize non-finite numerics
        _clean_nonfinite_inplace(r)

        # MINIMAL FIX: ScreenerRow.change_pct requires a float; default to 0.0 if missing/None
        if r.get("change_pct") is None:
            r["change_pct"] = 0.0

        # Build the Pydantic row
        norm_items.append(ScreenerRow(**r))

    if dropped:
        log.warning("screener: dropped invalid rows (missing last/score)",
                    extra={"dropped": dropped})

    # Ensure tz-aware as_of for response model
    as_of_dt = _ensure_tz_as_of(resolved_as_of, datetime.now(timezone.utc))

    return ScreenerList(
        items=norm_items,
        pagination={"page": page, "per_page": per_page, "total": total, "next_cursor": None},
        as_of=as_of_dt,
        run_id=resolved_run_id,
    )



