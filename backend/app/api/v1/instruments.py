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
    log.info("detail GET: symbol=%s, run_id_qp=%s", symbol, run_id)
    resolved_run_id, _as_of = _resolve_run_id(symbol, run_id, deps)
    log.info("detail resolved_run_id=%s", resolved_run_id)

    if resolved_run_id is None:
        log.warning("detail 404: no snapshot for symbol=%s", symbol)
        raise HTTPException(status_code=404, detail={"title": "Not Found", "detail": "No snapshot available"})

    # Build raw dict first
    raw = build_drawer_detail(symbol, resolved_run_id, deps)
    log.info("detail built: keys=%s", list(raw.keys()))

    # EXPLICIT validation here so we can log exact mismatch instead of a silent 500
    try:
        model = DrawerDetail.model_validate(raw)
    except ValidationError as ve:
        log.exception("detail response-model validation failed: symbol=%s run_id=%s errors=%s", symbol, resolved_run_id, ve.errors())
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
