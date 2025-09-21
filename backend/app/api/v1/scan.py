# backend/app/api/v1/scan.py
from __future__ import annotations
import logging
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, Body, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.idempotency import get_idempotency_key
from app.schemas.runs import RunDetail
from app.services.screening_service import run_screening
from app.workers.jobs import post_scan_jobs  # post-scan hook

router = APIRouter(tags=["Screener"])
log = logging.getLogger(__name__)


@router.post("/scan", response_model=RunDetail)
def post_scan(
    payload: Optional[Dict[str, Any]] = Body(default=None),
    idempotency_key: Optional[str] = Depends(get_idempotency_key),
    s: Session = Depends(get_session),
    request: Request = ...,
):
    # Normalize payload
    body: Dict[str, Any] = dict(payload or {})
    if isinstance(body.get("universe"), str):
        body["universe"] = body["universe"].strip().upper()

    # Build effective idempotency key (optionally salted)
    salt_val = getattr(getattr(request, "app", None).state, "idem_salt", "") if hasattr(request, "app") else ""
    effective_key = f"{salt_val}:{idempotency_key}" if (idempotency_key and salt_val) else idempotency_key

    # Start log
    log.info(
        "manual scan requested",
        extra={
            "universe": body.get("universe") or "<default>",
            "idem_key": (idempotency_key or "")[:64],
        },
    )

    # Run core screening
    result, created = run_screening(session=s, key=effective_key, payload=body)

    # Completion log (avoid reserved 'created' key)
    log.info(
        "manual scan completed",
        extra={"run_id": result.run_id, "was_created": bool(created)},
    )

    # Post-scan side effects (alerts, etc.)
    try:
        log.info("post-scan alert jobs starting", extra={"run_id": result.run_id})
        post_scan_jobs(result.run_id)
        log.info("post-scan alert jobs finished", extra={"run_id": result.run_id})
    except Exception as e:
        log.exception("post-scan alert jobs failed", extra={"run_id": result.run_id, "error": str(e)})

    # 201 on first run, 200 on idempotent replay
    return JSONResponse(
        status_code=201 if created else 200,
        content=result.model_dump(mode="json", exclude_none=True),
    )
