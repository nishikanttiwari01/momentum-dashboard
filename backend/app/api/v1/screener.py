# backend/app/api/v1/screener.py
from __future__ import annotations
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Request, Query
from app.schemas.screener import ScreenerList, ScreenerRow
from app.repos.parquet.scores_repo import ScoresRepo

router = APIRouter(tags=["Screener"])
repo = ScoresRepo()

# Treat these query params as non-filter controls. Everything else maps into filter ops.
KNOWN_KEYS = {"run_id", "as_of", "sort", "page", "per_page", "universe"}


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


def _badge_contract_safe(b: dict) -> dict:
    """
    Normalize a badge into the compact contract shape ONLY:
      { code: str, text: str, color: str }

    Rationale:
    - Generated Pydantic models may forbid extra fields; keep it minimal/safe.
    - We still map legacy inputs (key/label/color) → code/text/color.
    """
    code = b.get("code") or b.get("key") or ""
    text = b.get("text") or b.get("label") or ""
    color = b.get("color") or "grey"
    return {"code": code, "text": text, "color": color}


def _derive_week_fields(row: Dict[str, Any]) -> None:
    """
    Ensure wk_change and wk_change_pct exist.

    If parquet supplies a helper 'ret_1w' (percent), we compute:
      base = last / (1 + ret_1w/100)
      wk_change     = last - base
      wk_change_pct = ret_1w

    If not present, we leave them as None (the UI can hide/null-format).
    """
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


@router.get("/screener", response_model=ScreenerList)
def list_screener(
    request: Request,
    run_id: Optional[str] = Query(None, description="Exact snapshot run id, e.g. 20250912T093000Z"),
    as_of: Optional[str] = Query(None, description="YYYY-MM-DD; pick last run on/before this date"),
    sort: str = Query("score.desc,last.desc", description="Comma list e.g. score.desc,last.desc"),
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=500),
    # Note: universe is accepted for future server-side filtering; currently ignored by repo.read().
    universe: Optional[str] = Query(None, description="Universe preset (e.g., NIFTY500, NIFTY50, ALL)"),
):
    # Parse filters from the raw query string
    params = dict(request.query_params)
    filters = _parse_filters(params)

    # Ask the repo for the requested projection. It gracefully handles Phase-9 (minimal)
    # and Phase-11 (rich) parquet schemas and aliases. See ScoresRepo.read().  :contentReference[oaicite:2]{index=2}
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
                "symbol", "name", "sector", "last", "change_pct",
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
    for r in items:
        # Derive 1W fields if not present
        _derive_week_fields(r)

        # Normalize badges → only code/text/color (contract-safe)
        badges = r.get("badges") or []
        r["badges"] = [_badge_contract_safe(b) for b in badges if isinstance(b, dict)]

        # Clean up legacy helper no matter what
        r.pop("ret_1w", None)

        # Normalize score as int 0..100 (in case upstream stores float)
        s = r.get("score")
        if isinstance(s, float):
            r["score"] = int(round(s * 100 if 0.0 <= s <= 1.0 else s))
        elif s is None:
            r["score"] = 0

        # Ensure symbol exists (model often requires it)
        r.setdefault("symbol", "")

        # Build the Pydantic row; model handles datetime parsing for 'as_of' if it's an ISO string
        norm_items.append(ScreenerRow(**r))

    # Return a ScreenerList model (not a raw dict) so FastAPI enforces/serializes via Pydantic
    return ScreenerList(
        items=norm_items,
        pagination={"page": page, "per_page": per_page, "total": total, "next_cursor": None},
        as_of=resolved_as_of,
        run_id=resolved_run_id,
    )
