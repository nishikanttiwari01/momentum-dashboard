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

    log.info("detail GET", extra={"symbol": canonical_symbol, "run_id_qp": run_id})

    # 1) Primary resolution path (existing behavior)
    resolved_run_id, _as_of = _resolve_run_id(canonical_symbol, run_id, deps)
    log.info("detail resolved_run_id(primary)", extra={"run_id": resolved_run_id, "as_of": _as_of})

    # 2) Fallbacks when run_id is still not resolved
    if resolved_run_id is None:
        sr = deps.scores_repo
        try:
            # 2a) Repo-level latest (returns rid or as_of depending on snapshot kind)
            rid_latest = asof_latest = None
            if hasattr(sr, "latest_run"):
                rid_latest, asof_latest = sr.latest_run()  # type: ignore[attr-defined]
                log.info("detail resolved_latest", extra={"run_id": rid_latest, "as_of": asof_latest})

            # 2b) If still no run_id, try a symbol-scoped read (new layout resolver inside repo)
            if resolved_run_id is None:
                try:
                    items, total, rid_used, asof_used = sr.read(
                        run_id=None,
                        as_of_str=None,
                        # IMPORTANT: tuple-op filter matches repo API ({("field","op"): value})
                        filters={( "symbol", "eq"): canonical_symbol},
                        sort=None,
                        page=1,
                        per_page=1,
                        columns=None,
                    )
                except TypeError:
                    # Legacy signature (page_size) or older filters — retain compat
                    items, total, rid_used, asof_used = sr.read(
                        run_id=None,
                        as_of_str=None,
                        filters={( "symbol", "eq"): canonical_symbol},
                        sort=None,
                        page=1,
                        page_size=1,  # legacy arg name
                        columns=None,
                    )

                log.info(
                    "detail resolved_from_repo_read",
                    extra={"rows": total, "rid_used": rid_used, "as_of": asof_used}
                )

                # Prefer the repo-resolved run_id if available; otherwise, stick with None
                if rid_used:
                    resolved_run_id = rid_used
                elif items and isinstance(items[0], dict):
                    # Daily partitions may omit run_id; keep resolved_run_id=None, builder will need to handle via repo
                    candidate_rid = items[0].get("run_id")
                    if candidate_rid:
                        resolved_run_id = candidate_rid
        except Exception:
            log.exception("detail fallback run_id resolution failed")

    # 3) If still nothing resolvable, return a clean 404
    if resolved_run_id is None:
        log.warning("detail 404: no snapshot", extra={"symbol": canonical_symbol})
        raise HTTPException(
            status_code=404,
            detail={"title": "Not Found", "detail": "No snapshot available"},
        )

    # 4) Build raw dict first (builder currently expects a run_id; daily-only paths should be handled inside builder)
    raw = build_drawer_detail(canonical_symbol, resolved_run_id, deps)
    log.info("detail built", extra={"keys": list(raw.keys())})

    # 5) Validate explicitly so we log exact mismatches
    try:
        model = DrawerDetail.model_validate(raw)
    except ValidationError as ve:
        log.exception(
            "detail response-model validation failed",
            extra={"symbol": canonical_symbol, "run_id": resolved_run_id, "errors": ve.errors()},
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
