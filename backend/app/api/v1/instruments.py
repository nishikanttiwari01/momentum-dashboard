# backend/app/api/v1/instruments.py
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Path, Query, HTTPException, FastAPI
from pydantic import ValidationError

from app.schemas.detail import DrawerDetail
from app.services.detail_service import DetailDeps, _resolve_run_id, build_drawer_detail
from app.repos.market_data_repo import MarketDataRepo   

log = logging.getLogger("api.v1.instruments")
router = APIRouter(tags=["Instruments"])


def _deps() -> DetailDeps:
    from app.repos.parquet.scores_repo import ScoresRepo
    try:
        from app.repos.sql.positions_repo import PositionsRepo
    except Exception:  # pragma: no cover
        PositionsRepo = None  # type: ignore
    try:
        from app.repos.sql.snapshot_pins_repo import SnapshotPinsRepo
    except Exception:  # pragma: no cover
        SnapshotPinsRepo = None  # type: ignore

    return DetailDeps(
        scores_repo=ScoresRepo(),
        indicators_repo=MarketDataRepo(),  # ← use Yahoo for sparkline
        positions_repo=PositionsRepo() if PositionsRepo else None,
        snapshot_pins_repo=SnapshotPinsRepo() if SnapshotPinsRepo else None,
    )


# IMPORTANT: indirection — tests monkeypatch instruments_api._deps
def _deps_runtime() -> DetailDeps:
    return _deps()


@router.get(
    "/instruments/{symbol}/detail",
    summary="Get instrument detail (drawer) for a symbol",
    response_model=DrawerDetail,
)
def get_instrument_detail(
    symbol: str = Path(..., description="Canonical ticker (e.g., RELIANCE.NS)"),
    run_id: Optional[str] = Query(None, description="Snapshot run_id (intraday). If provided, takes precedence."),
    as_of: Optional[str] = Query(None, description="EOD snapshot date YYYY-MM-DD. Used when run_id is not provided."),
    deps: DetailDeps = Depends(_deps_runtime),
) -> DrawerDetail:
    # Normalize symbol for robustness against case/format drift
    canonical_symbol = (symbol or "").strip().upper()

    log.info("detail GET", extra={"symbol": canonical_symbol, "run_id_qp": run_id, "as_of_qp": as_of})

    # --- Resolution order: run_id (intraday) → as_of (EOD) → pinned/latest fallback ---
    resolved_run_id: Optional[str] = None
    resolved_as_of: Optional[str] = None

    if (run_id or "").strip():
        resolved_run_id = (run_id or "").strip()
        resolved_as_of = None
    elif (as_of or "").strip():
        resolved_run_id = None
        resolved_as_of = (as_of or "").strip()
    else:
        # Primary existing behavior (can return run_id or as_of depending on latest)
        rid, asof_val = _resolve_run_id(canonical_symbol, run_id, deps)
        resolved_run_id = rid
        resolved_as_of = asof_val
        log.info("detail resolved_run_id(primary)", extra={"run_id": resolved_run_id, "as_of": resolved_as_of})

        # Fallbacks when still unresolved
        if resolved_run_id is None and resolved_as_of is None:
            sr = deps.scores_repo
            try:
                # Try repo.latest_run() for a quick hint
                rid_latest = asof_latest = None
                if hasattr(sr, "latest_run"):
                    rid_latest, asof_latest = sr.latest_run()  # type: ignore[attr-defined]
                    log.info("detail resolved_latest", extra={"run_id": rid_latest, "as_of": asof_latest})

                # Symbol-scoped read (repo resolver inside read)
                try:
                    items, total, rid_used, asof_used = sr.read(
                        run_id=None,
                        as_of_str=None,
                        filters={("symbol", "eq"): canonical_symbol},  # tuple-op filter per repo API
                        sort=None,
                        page=1,
                        per_page=1,
                        columns=None,
                    )
                except TypeError:
                    # Legacy signature (page_size) — retain compatibility
                    items, total, rid_used, asof_used = sr.read(
                        run_id=None,
                        as_of_str=None,
                        filters={("symbol", "eq"): canonical_symbol},
                        sort=None,
                        page=1,
                        page_size=1,  # legacy arg name
                        columns=None,
                    )

                log.info(
                    "detail resolved_from_repo_read",
                    extra={"rows": total, "rid_used": rid_used, "as_of": asof_used}
                )

                # Prefer repo-returned rid; else accept as_of (EOD path)
                if rid_used:
                    resolved_run_id = rid_used
                elif asof_used:
                    resolved_as_of = asof_used
                elif rid_latest or asof_latest:
                    resolved_run_id = rid_latest or None
                    resolved_as_of = asof_latest or None

                # As a last resort, if items[0] has a run_id field, use it
                if not resolved_run_id and not resolved_as_of and items and isinstance(items[0], dict):
                    candidate_rid = items[0].get("run_id")
                    if candidate_rid:
                        resolved_run_id = candidate_rid
            except Exception:
                log.exception("detail fallback run_id/as_of resolution failed")

    # 404 if nothing resolvable
    if resolved_run_id is None and not resolved_as_of:
        log.warning("detail 404: no snapshot", extra={"symbol": canonical_symbol})
        raise HTTPException(
            status_code=404,
            detail={"title": "Not Found", "detail": "No snapshot available"},
        )

    # Build detail for the resolved snapshot (run_id for intraday, as_of for EOD)
    raw = build_drawer_detail(canonical_symbol, resolved_run_id, deps, as_of=resolved_as_of)
    log.info("detail built", extra={"keys": list(raw.keys())})

    # Hard clamp score_basic fields to contract bounds (defensive against legacy parquet values)
    raw_sb_before = raw.get("score_breakdown")
    log.debug(
        "detail score_breakdown pre-normalization",
        extra={"symbol": canonical_symbol, "score_breakdown": str(raw_sb_before)},
    )

    try:
        sb_container = raw.get("score_breakdown")
        if isinstance(sb_container, dict):
            sb_dict = dict(sb_container)
        elif hasattr(sb_container, "model_dump"):
            sb_dict = sb_container.model_dump()
        elif hasattr(sb_container, "__dict__"):
            sb_dict = dict(sb_container.__dict__)
        else:
            sb_dict = {}

        sb_basic = sb_dict.get("score_basic")
        if isinstance(sb_basic, str):
            try:
                sb_basic = float(sb_basic)
            except ValueError:
                sb_basic = None
        if isinstance(sb_basic, (int, float)):
            sb_dict["score_basic"] = max(0, min(int(sb_basic), 12))
        else:
            sb_dict["score_basic"] = None

        sb_basic_norm = sb_dict.get("score_basic_normalized")
        if isinstance(sb_basic_norm, str):
            try:
                sb_basic_norm = float(sb_basic_norm)
            except ValueError:
                sb_basic_norm = None
        if isinstance(sb_basic_norm, (int, float)):
            sb_dict["score_basic_normalized"] = max(0.0, min(float(sb_basic_norm), 100.0))
        else:
            sb_dict["score_basic_normalized"] = None

        raw["score_breakdown"] = sb_dict
    except Exception:
        log.exception("detail score_breakdown normalization failed", extra={"symbol": canonical_symbol})
    else:
        log.debug(
            "detail score_breakdown post-normalization",
            extra={"symbol": canonical_symbol, "score_breakdown": str(raw.get("score_breakdown"))},
        )

    # Validate explicitly so we log exact mismatches
    try:
        model = DrawerDetail.model_validate(raw)
    except ValidationError as ve:
        log.exception(
            "detail response-model validation failed",
            extra={"symbol": canonical_symbol, "run_id": resolved_run_id, "as_of": resolved_as_of, "errors": ve.errors()},
        )
        raise HTTPException(
            status_code=500,
            detail={
                "status": 500,
                "title": "Response validation failed",
                "detail": str(ve),
                "code": "INTERNAL_ERROR",
            },
        )

    return model


# Test-only mini app so tests can use LifespanManager(instruments_api.app)
app = FastAPI()
app.include_router(router, prefix="/api/v1")
