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

    scores = ScoresRepo()
    positions = PositionsRepo() if PositionsRepo else None
    pins = SnapshotPinsRepo() if SnapshotPinsRepo else None
    return DetailDeps(scores_repo=scores, indicators_repo=None, positions_repo=positions, snapshot_pins_repo=pins)

# indirection so tests' monkeypatch on _deps takes effect at request time
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
    log.info("GET detail: symbol=%s, run_id_qp=%s", symbol, run_id)
    try:
        resolved_run_id, _as_of = _resolve_run_id(symbol, run_id, deps)
        log.info("detail: resolved_run_id=%s", resolved_run_id)
        if resolved_run_id is None:
            log.warning("detail: no snapshot available (404) for symbol=%s", symbol)
            raise HTTPException(status_code=404, detail={"title": "Not Found", "detail": "No snapshot available"})

        detail = build_drawer_detail(symbol, resolved_run_id, deps)
        log.debug("detail built for %s@%s: keys=%s", symbol, resolved_run_id, list(detail.keys()))
        return detail  # FastAPI will validate/coerce into DrawerDetail

    except ValidationError as ve:
        # Pydantic response-model validation error (shape/type mismatch)
        log.exception("detail: response validation failed for symbol=%s run_id=%s", symbol, run_id)
        raise HTTPException(status_code=500, detail={"status": 500, "title": "Response validation failed", "detail": str(ve), "code": "INTERNAL_ERROR"})  # noqa: E501
    except HTTPException:
        raise
    except Exception as e:
        log.exception("detail: unexpected error for symbol=%s run_id=%s", symbol, run_id)
        raise HTTPException(status_code=500, detail={"status": 500, "title": "Unexpected error", "detail": "Please try again.", "code": "INTERNAL_ERROR"})  # noqa: E501

# Test-only mini app so tests use LifespanManager(instruments_api.app)
app = FastAPI()
app.include_router(router, prefix="/api/v1")
