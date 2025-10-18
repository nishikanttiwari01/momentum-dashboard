from __future__ import annotations

import logging
import threading
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response

from app.schemas.generated.models import MomentumHeatmapResponse
from app.services.momentum_heatmap import MomentumHeatmapService

router = APIRouter(tags=["Momentum"])
log = logging.getLogger(__name__)

_SERVICE_LOCK = threading.Lock()
_SERVICE_SINGLETON: Optional[MomentumHeatmapService] = None


def _get_service() -> MomentumHeatmapService:
    global _SERVICE_SINGLETON
    if _SERVICE_SINGLETON is None:
        with _SERVICE_LOCK:
            if _SERVICE_SINGLETON is None:
                _SERVICE_SINGLETON = MomentumHeatmapService()
    return _SERVICE_SINGLETON


@router.get(
    "/momentum/heatmap",
    response_model=MomentumHeatmapResponse,
    summary="NSE sector and industry momentum heatmap snapshot",
)
def get_momentum_heatmap(
    response: Response,
    include_industries: bool = Query(
        False,
        description="Include industry-level breakdown (currently returns an empty list until implemented).",
    ),
    include_constituents: bool = Query(
        False,
        description="Include leaders/laggards arrays populated from NSE index constituents.",
    ),
    as_of: Optional[date] = Query(
        None,
        description="Optional trading date (YYYY-MM-DD IST). Historical snapshots are not yet available.",
    ),
    if_none_match: Optional[str] = Header(
        default=None, alias="If-None-Match", convert_underscores=False
    ),
    service: MomentumHeatmapService = Depends(_get_service),
) -> MomentumHeatmapResponse:
    if as_of and as_of > date.today():
        raise HTTPException(status_code=400, detail="as_of cannot be in the future.")

    try:
        payload = service.get_heatmap(
            as_of=as_of,
            include_industries=include_industries,
            include_constituents=include_constituents,
        )
    except NotImplementedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive logging path
        log.exception(
            "momentum_heatmap_failed",
            extra={"as_of": as_of.isoformat() if as_of else None},
        )
        raise HTTPException(status_code=502, detail="Failed to compute momentum heatmap") from exc

    etag_key = payload.run_id or f"{payload.trade_date.isoformat()}-{payload.session}"
    etag_value = f'W/"{etag_key}"'

    if if_none_match and if_none_match == etag_value:
        return Response(status_code=304)

    response.headers["ETag"] = etag_value
    response.headers["Cache-Control"] = "private, max-age=60"
    return payload


__all__ = ["router"]
