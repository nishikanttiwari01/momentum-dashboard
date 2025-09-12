from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, Query, HTTPException

from app.services.detail_service import DetailDeps, build_drawer_detail, _resolve_run_id  # + _resolve_run_id
from app.repos.parquet.scores_repo import ScoresRepo
from app.repos.parquet.indicators_repo import IndicatorsRepo
from app.repos.sql.positions_repo import PositionsRepo
from app.repos.sql.snapshot_pins_repo import SnapshotPinsRepo

# Optional sparkline helper (fallback-safe if not present)
try:
    from app.repos.parquet import datasets  # used only by /sparkline
except Exception:  # pragma: no cover
    datasets = None  # type: ignore

router = APIRouter()


def _deps() -> DetailDeps:
    return DetailDeps(
        scores=ScoresRepo(),
        indicators=IndicatorsRepo(),
        positions=PositionsRepo(),
        pins=SnapshotPinsRepo(),
    )


@router.get("/instruments/{symbol}/detail")
def get_instrument_detail(symbol: str, run_id: Optional[str] = Query(None)):
    try:
        payload = build_drawer_detail(symbol=symbol, run_id=run_id, deps=_deps())
    except KeyError as e:
        # Compare first arg to avoid the "'snapshot_not_found'" string repr issue
        if e.args and e.args[0] == "snapshot_not_found":
            raise HTTPException(status_code=404, detail="Snapshot not found")
        raise
    return payload


@router.get("/instruments/{symbol}/sparkline")
def get_sparkline(symbol: str, days: int = 30, run_id: Optional[str] = Query(None)):
    # Resolve snapshot using the same rule as the detail endpoint
    rid, as_of = _resolve_run_id(symbol, run_id, _deps())
    prices = []
    if datasets is not None and hasattr(datasets, "slice_prices"):
        prices = datasets.slice_prices(symbol, rid, days)  # type: ignore[attr-defined]
    return {
        "symbol": symbol.upper(),
        "run_id": rid,
        "as_of": as_of,
        "days": days,
        "prices": prices,
    }
