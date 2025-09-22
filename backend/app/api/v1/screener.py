# backend/app/api/v1/screener.py
from __future__ import annotations
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Request, Query
from app.schemas.screener import ScreenerList, ScreenerRow
from app.repos.parquet.scores_repo import ScoresRepo

# ADDED: minimal imports to clean NaN/Inf payloads and log drops
import math
import numbers
import logging
from datetime import datetime, timezone

router = APIRouter(tags=["Screener"])
repo = ScoresRepo()
log = logging.getLogger(__name__)

# Treat these query params as non-filter controls. Everything else maps into filter ops.
KNOWN_KEYS = {"run_id", "as_of", "sort", "page", "per_page", "universe"}


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


@router.get("/screener", response_model=ScreenerList)
def list_screener(
    request: Request,
    run_id: Optional[str] = Query(None, description="Exact snapshot run id, e.g. 20250912T093000Z"),
    as_of: Optional[str] = Query(None, description="YYYY-MM-DD; pick last run on/before this date"),
    sort: str = Query("score.desc,last.desc", description="Comma list e.g. score.desc,last.desc"),
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=500),
    universe: Optional[str] = Query(None, description="Universe preset (e.g., NIFTY500, NIFTY50, ALL)"),
):
    # Parse filters from the raw query string
    params = dict(request.query_params)
    filters = _parse_filters(params)

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
        for b in badges:
            if isinstance(b, dict) and "category" in b and "label" in b:
                norm_badges.append({"category": b["category"], "label": b["label"]})
            elif isinstance(b, dict):
                norm_badges.append(_badge_to_contract_shape(b))
            elif isinstance(b, str):
                # extremely defensive: turn free-text into a WATCH badge
                norm_badges.append({"category": "WATCH", "label": b})
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
