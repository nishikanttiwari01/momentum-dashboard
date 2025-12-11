from __future__ import annotations

import logging
from typing import Optional, List

from fastapi import APIRouter, Body, HTTPException, Query, Path, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

# Generated models from your OpenAPI regeneration
from app.schemas.generated.models import PositionOut, PositionCreate, PositionUpdate  # type: ignore
from app.repos.sql.positions_repo import PositionsRepo

log = logging.getLogger("app.api.positions")
router = APIRouter(prefix="/positions", tags=["positions"])

try:
    from app.core.db import get_session  # must yield a Session
except Exception as e:
    get_session = None
    log.error("DB dependency missing: %s", e)


def _require_session():
    if get_session is None:
        raise HTTPException(status_code=503, detail="DB not initialized")
    return get_session


# -------- List (optional ?symbol=) --------
@router.get("", response_model=List[PositionOut])
def list_positions(
    symbol: Optional[str] = Query(None),
    active: Optional[bool] = Query(
        None, description="Filter by active (true) or inactive (false) trades"
    ),
    s: Session = Depends(_require_session()),
):
    repo = PositionsRepo(session=s)
    rows = repo.list_positions(symbol=symbol, active=active)
    return [PositionOut.model_validate(r) for r in rows]


# -------- Get by symbol --------
@router.get("/{symbol}", response_model=PositionOut)
def get_position(
    symbol: str = Path(..., description="Ticker symbol"),
    s: Session = Depends(_require_session()),
):
    repo = PositionsRepo(session=s)
    row = repo.get(symbol)
    if not row:
        raise HTTPException(status_code=404, detail="Position not found")
    return PositionOut.model_validate(row)


# -------- Create (lock) --------
@router.post("", response_model=PositionOut)
def create_position(
    payload: PositionCreate = Body(...),
    s: Session = Depends(_require_session()),
):
    if payload.price is None or payload.price <= 0:
        raise HTTPException(status_code=400, detail="price must be > 0")
    if payload.qty is None or payload.qty <= 0:
        raise HTTPException(status_code=400, detail="qty must be provided and > 0")
    repo = PositionsRepo(session=s)
    row = repo.create_or_lock(
        symbol=payload.symbol,
        price=float(payload.price),
        qty=payload.qty,
        note=payload.note,
    )
    return PositionOut.model_validate(row)


# -------- Update by ID (partial) --------
@router.put("/{id}", response_model=PositionOut)
def update_position(
    id: int = Path(...),
    fields: PositionUpdate = Body(...),
    s: Session = Depends(_require_session()),
):
    repo = PositionsRepo(session=s)
    current = repo.get_by_id(id)
    if not current:
        raise HTTPException(status_code=404, detail="Position not found")

    payload = fields.model_dump(exclude_unset=True)

    if payload.get("trade_on") is False:
        sell_price = payload.get("sell_price") if "sell_price" in payload else fields.sell_price
        if sell_price is None or sell_price <= 0:
            raise HTTPException(status_code=400, detail="sell_price must be provided to close a trade")

    requested_qty = payload["qty"] if "qty" in payload else current.get("qty")
    if payload.get("trade_on") is True:
        if requested_qty is None or requested_qty <= 0:
            raise HTTPException(status_code=400, detail="qty must be provided and > 0 to activate a trade")

    # Disallow entry_price_locked changes here (unlock->lock flow only)
    payload.pop("entry_price_locked", None)
    row = repo.update_by_id(id, **payload)
    if not row:
        raise HTTPException(status_code=500, detail="Update failed")
    return PositionOut.model_validate(row)


# -------- Delete by ID (unlock) --------
@router.delete("/{id}", status_code=204)
def delete_position(
    id: int = Path(...),
    s: Session = Depends(_require_session()),
):
    repo = PositionsRepo(session=s)
    if not repo.get_by_id(id):
        raise HTTPException(status_code=404, detail="Position not found")
    if not repo.delete(id):
        raise HTTPException(status_code=500, detail="Delete failed")
    return JSONResponse(status_code=status.HTTP_204_NO_CONTENT, content={})
