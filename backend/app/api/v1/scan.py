# backend/app/api/v1/scan.py
from __future__ import annotations
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, Body, Request  # <-- CHANGED: import Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.idempotency import get_idempotency_key
from app.schemas.runs import RunDetail
from app.services.screening_service import run_screening

router = APIRouter(tags=["Screener"])


@router.post("/scan", response_model=RunDetail)
def post_scan(
    payload: Optional[Dict[str, Any]] = Body(default=None),
    idempotency_key: Optional[str] = Depends(get_idempotency_key),
    s: Session = Depends(get_session),
    request: Request = None,  # <-- NEW: access app.state.idem_salt
):
    """
    Idempotent scan trigger (Phase-9 semantics preserved).
    We accept optional 'universe' (Phase-10 ready) and normalize it to UPPER.
    """

    body: Dict[str, Any] = dict(payload or {})
    u = body.get("universe")
    if isinstance(u, str):
        body["universe"] = u.strip().upper()

    # NEW: salt the incoming idempotency key with a per-app value so tests can't collide
    if idempotency_key:
        salt = getattr(getattr(request, "app", None), "state", None)
        salt_val = getattr(salt, "idem_salt", "") if salt else ""
        effective_key = f"{salt_val}:{idempotency_key}"
    else:
        effective_key = None

    result, created = run_screening(session=s, key=effective_key, payload=body)
    return JSONResponse(status_code=201 if created else 200, content=result.model_dump())
