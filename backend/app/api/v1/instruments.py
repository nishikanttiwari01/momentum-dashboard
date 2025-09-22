# backend/app/api/v1/instruments.py
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Path, Query, HTTPException, FastAPI
from pydantic import ValidationError

from app.schemas.detail import DrawerDetail
from app.services.detail_service import DetailDeps, _resolve_run_id, build_drawer_detail

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
        indicators_repo=None,
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
    run_id: Optional[str] = Query(None, description="Snapshot run_id; absent → pinned or latest"),
    deps: DetailDeps = Depends(_deps_runtime),
) -> DrawerDetail:
    # Normalize symbol for robustness against case/format drift
    canonical_symbol = (symbol or "").strip().upper()

    log.info("detail GET: symbol=%s, run_id_qp=%s", canonical_symbol, run_id)

    # Primary resolution path (kept as-is)
    resolved_run_id, _as_of = _resolve_run_id(canonical_symbol, run_id, deps)
    log.info("detail resolved_run_id(primary)=%s", resolved_run_id)

    # Fallback: try to discover a usable run_id from ScoresRepo if none was found.
    # This is defensive against storage-layout changes (daily/intraday).
    if resolved_run_id is None:
        try:
            sr = deps.scores_repo

            # 1) Prefer an explicit helper if present
            if hasattr(sr, "latest_run_id_for_symbol"):
                resolved_run_id = sr.latest_run_id_for_symbol(canonical_symbol)  # type: ignore[attr-defined]
                log.info("detail resolved_run_id(latest_for_symbol)=%s", resolved_run_id)

            # 2) Generic latest if symbol-specific helper isn’t available
            if resolved_run_id is None and hasattr(sr, "latest_run_id"):
                resolved_run_id = sr.latest_run_id()  # type: ignore[attr-defined]
                log.info("detail resolved_run_id(latest_any)=%s", resolved_run_id)

            # 3) As a last resort, try reading a single row filtered by symbol and grab its run_id
            if resolved_run_id is None and hasattr(sr, "read"):
                try:
                    items, *_ = sr.read(
                        run_id=None,
                        as_of_str=None,
                        filters={"symbol": canonical_symbol},
                        sort=None,
                        page=1,
                        per_page=1,
                    )
                    if items:
                        resolved_run_id = items[0].get("run_id")
                        log.info("detail resolved_run_id(from_read_filter)=%s", resolved_run_id)
                except TypeError:
                    # Older signature: use page_size instead of per_page
                    items, *_ = sr.read(
                        run_id=None,
                        as_of_str=None,
                        filters={"symbol": canonical_symbol},
                        sort=None,
                        page=1,
                        page_size=1,  # legacy arg name
                    )
                    if items:
                        resolved_run_id = items[0].get("run_id")
                        log.info("detail resolved_run_id(from_read_filter_legacy)=%s", resolved_run_id)
        except Exception:
            log.exception("detail fallback run_id resolution failed")

    if resolved_run_id is None:
        log.warning("detail 404: no snapshot for symbol=%s", canonical_symbol)
        raise HTTPException(
            status_code=404,
            detail={"title": "Not Found", "detail": "No snapshot available"},
        )

    # Build raw dict first
    raw = build_drawer_detail(canonical_symbol, resolved_run_id, deps)
    log.info("detail built: keys=%s", list(raw.keys()))

    # EXPLICIT validation here so we can log exact mismatch instead of a silent 500
    try:
        model = DrawerDetail.model_validate(raw)
    except ValidationError as ve:
        log.exception(
            "detail response-model validation failed: symbol=%s run_id=%s errors=%s",
            canonical_symbol,
            resolved_run_id,
            ve.errors(),
        )
        # Return a structured 500 (matches your error contract)
        raise HTTPException(
            status_code=500,
            detail={
                "status": 500,
                "title": "Response validation failed",
                "detail": str(ve),
                "code": "INTERNAL_ERROR",
            },
        )

    # FastAPI will also validate again against response_model, but we return a model instance
    return model


# Test-only mini app so tests can use LifespanManager(instruments_api.app)
app = FastAPI()
app.include_router(router, prefix="/api/v1")
