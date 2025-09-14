# backend/app/api/v1/screener.py
from __future__ import annotations
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Request, Query
from app.schemas.screener import ScreenerList, ScreenerRow
from app.repos.parquet.scores_repo import ScoresRepo

router = APIRouter()
repo = ScoresRepo()

# Added "universe" so it's treated as a known, non-filter query param
KNOWN_KEYS = {"run_id", "as_of", "sort", "page", "per_page", "universe"}


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
    """Normalize a badge dict into the expected shape.
    Phase7: keep key/label/color, also expose code/text for the new compact schema.
    """
    return {
        "key": b.get("key", ""),
        "label": b.get("label", ""),
        "color": b.get("color", "grey"),
        # Phase7 additions:
        "code": b.get("code") or b.get("key") or "",
        "text": b.get("text") or b.get("label") or "",
    }


def _derive_week_fields(row: Dict[str, Any]) -> None:
    """Phase7: ensure wk_change and wk_change_pct exist.
    If parquet supplies ret_1w (percent), we compute:
      base = last / (1 + ret_1w/100)
      wk_change = last - base
      wk_change_pct = ret_1w
    """
    if row.get("wk_change") is not None and row.get("wk_change_pct") is not None:
        return
    last = row.get("last")
    ret_1w = row.get("ret_1w")  # percent, e.g. 1.35
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


@router.get("/screener", response_model=ScreenerList)
def list_screener(
    request: Request,
    run_id: Optional[str] = Query(None, description="Exact snapshot run id, e.g. 20250912T093000Z"),
    as_of: Optional[str] = Query(None, description="YYYY-MM-DD; pick last run on/before this date"),
    sort: str = Query("score.desc,last.desc", description="Comma list, e.g. score.desc,last.desc"),
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=500),
    # NEW: accept universe but don't use it yet (service/repo wiring comes next)
    universe: Optional[str] = Query(
        None,
        description="Optional universe preset (e.g., NIFTY500, NIFTY50, ALL). Currently ignored by this endpoint."
    ),
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
                # Phase7: if parquet already has these, include them directly:
                "wk_change","wk_change_pct",
            ],
        )
    except Exception:
        items, total, resolved_run_id, resolved_as_of = [], 0, None, None

    # Normalize rows
    norm_items: List[ScreenerRow] = []
    for r in items:
        # Phase7: derive week fields when not present
        _derive_week_fields(r)
        # Phase7: normalize badges (keep old fields, add code/text)
        badges = r.get("badges") or []
        r["badges"] = [_badge(b) for b in badges if isinstance(b, dict)]
        r.setdefault("symbol", "")
        r.pop("ret_1w", None)        # <-- Phase7: ensure internal helper is not returned
        s = r.get("score")
        if isinstance(s, float):
            # If score was a 0..1 float, round to 0..100; otherwise, just round to nearest int.
            r["score"] = int(round(s * 100 if 0.0 <= s <= 1.0 else s))
        elif s is None:
            r["score"] = 0
        norm_items.append(ScreenerRow(**r))

    return {
        "items": norm_items,
        "pagination": {"page": page, "per_page": per_page, "total": total, "next_cursor": None},
        "as_of": resolved_as_of,
        "run_id": resolved_run_id,
    }
