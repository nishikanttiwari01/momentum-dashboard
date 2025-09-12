# backend/app/api/v1/screener.py
from __future__ import annotations
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Request, Query
from app.schemas.screener import ScreenerList, ScreenerRow
from app.repos.parquet.scores_repo import ScoresRepo

router = APIRouter()
repo = ScoresRepo()

KNOWN_KEYS = {"run_id", "as_of", "sort", "page", "per_page"}


def _parse_filters(params) -> Dict[tuple[str, str], Any]:
    out: Dict[tuple[str, str], Any] = {}
    for k, v in params.items():
        if k in KNOWN_KEYS:
            continue
        if k.endswith(".in"):
            out[(k[:-3], "in")] = [x.strip() for x in v.split(",") if x.strip()]
        elif k.endswith(".gte"):
            try: out[(k[:-4], "gte")] = float(v)
            except Exception: pass
        elif k.endswith(".gt"):
            try: out[(k[:-3], "gt")] = float(v)
            except Exception: pass
        elif k.endswith(".lte"):
            try: out[(k[:-4], "lte")] = float(v)
            except Exception: pass
        elif k.endswith(".lt"):
            try: out[(k[:-3], "lt")] = float(v)
            except Exception: pass
        elif k.endswith(".like"):
            out[(k[:-5], "like")] = v
        elif k.endswith(".eq"):
            out[(k[:-3], "eq")] = v
    return out


def _badge(b: dict) -> dict:
    """Normalize a badge dict into the expected shape."""
    return {
        "key": b.get("key", ""),
        "label": b.get("label", ""),
        "color": b.get("color", "grey"),
    }


@router.get("/screener", response_model=ScreenerList)
def list_screener(
    request: Request,
    run_id: Optional[str] = Query(None, description="Exact snapshot run id, e.g. 20250912T093000Z"),
    as_of: Optional[str] = Query(None, description="YYYY-MM-DD; pick last run on/before this date"),
    sort: str = Query("score.desc,last.desc", description="Comma list, e.g. score.desc,last.desc"),
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=500),
):
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
                "symbol","name","sector","last","change_pct",
                "score","strength","rsi","adx","ret_12_1m","ret_6m","ret_3m","ret_1m",
                "ret_1w","pct_from_52w_high","atr_pct","liquidity","vol_spike","pct_today",
                "buy","reason","source","stale","badges",
                "run_id","as_of","last_index",
            ],
        )
    except Exception:
        items, total, resolved_run_id, resolved_as_of = [], 0, None, None

    # Normalize rows
    norm_items: List[ScreenerRow] = []
    for r in items:
        badges = r.get("badges") or []
        r["badges"] = [_badge(b) for b in badges if isinstance(b, dict)]
        r.setdefault("symbol", "")
        norm_items.append(ScreenerRow(**r))

    return {
        "items": norm_items,
        "pagination": {"page": page, "per_page": per_page, "total": total, "next_cursor": None},
        "as_of": resolved_as_of,
        "run_id": resolved_run_id,
    }
