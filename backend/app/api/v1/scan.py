# backend/app/api/v1/scan.py
from __future__ import annotations
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, Body, Request   # keep Request import
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
    request: Request = ...  # ✅ CHANGED: require Request (no Optional/Union); FastAPI injects this
):
    """
    Trigger a screener scan.

    - Idempotent via 'Idempotency-Key' header (optionally salted with app.state.idem_salt).
    - Accepts optional 'universe' (string); normalized to UPPER for consistent handling.
    - Returns RunDetail; we serialize with Pydantic JSON mode to handle datetimes properly.
    """

    # Normalize/defend payload (allow empty/null body)
    body: Dict[str, Any] = dict(payload or {})

    # Normalize universe to UPPER if present (avoids case-sensitive mismatches)
    if isinstance(body.get("universe"), str):
        body["universe"] = body["universe"].strip().upper()

    # Build effective idempotency key: prepend a per-process salt if available.
    # This avoids collisions when multiple test clients use the same header values.
    salt_val = getattr(getattr(request, "app", None).state, "idem_salt", "") if hasattr(request, "app") else ""
    effective_key = f"{salt_val}:{idempotency_key}" if (idempotency_key and salt_val) else idempotency_key

    # Delegate to the service layer. It writes Parquet and returns a RunDetail + 'created' flag.
    result, created = run_screening(session=s, key=effective_key, payload=body)

    # IMPORTANT: Use Pydantic v2 JSON mode so datetimes & enums serialize cleanly.
    # Returning JSONResponse lets us set 201 (created on first run) vs 200 (idempotent replay).
    return JSONResponse(
        status_code=201 if created else 200,
        content=result.model_dump(mode="json", exclude_none=True),
    )
