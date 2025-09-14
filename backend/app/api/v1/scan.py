from __future__ import annotations
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, Body
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.idempotency import get_idempotency_key
from app.schemas.runs import RunDetail
from app.services.screening_service import run_screening

# No prefix here; main.py supplies the API prefix
router = APIRouter(tags=["Screener"])

@router.post("/scan", response_model=RunDetail)
def post_scan(
    payload: Optional[Dict[str, Any]] = Body(default=None),
    idempotency_key: Optional[str] = Depends(get_idempotency_key),
    s: Session = Depends(get_session),
):
    """
    Idempotent scan trigger. First call -> 201; replay by same key -> 200.
    Body (optional): { as_of?: string, universe?: string[], notes?: string }
    """
    result, created = run_screening(session=s, key=idempotency_key, payload=payload or {})
    return JSONResponse(status_code=201 if created else 200, content=result.model_dump())
