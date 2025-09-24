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

    log.info(
        "manual scan requested",
        extra={
            "universe": body.get("universe") or "<default>",
            "as_of": body.get("as_of"),
            "idem_key": (idempotency_key or "")[:64],
            "idem_key_effective": (effective_key or "")[:64],
        },
    )

    # Run core screening
    result, created = run_screening(session=s, key=effective_key, payload=body)

    # Determine job status if present on the model
    status = getattr(result, "status", None)
    run_id = getattr(result, "run_id", None)
    rows_written = getattr(getattr(result, "counts", None), "rows_written", None)
    snapshot_path = getattr(result, "snapshot_path", None)

    # Decide HTTP code:
    # - 201 Created: first execution for this idem key
    # - 202 Accepted: idem replay BUT job not finished yet (IN_PROGRESS/QUEUED/etc.)
    # - 200 OK: idem replay and job already completed (DONE/FAILED or no status field)
    http_status = 201 if created else 200
    if not created and isinstance(status, str):
        st = status.upper()
        if st in ("QUEUED", "RUNNING", "IN_PROGRESS"):
            http_status = 202

    log.info(
        "manual scan completed",
        extra={
            "run_id": run_id,
            "was_created": bool(created),
            "status": status or "<none>",
            "http": http_status,
            "rows_written": rows_written,
            "snapshot_path": snapshot_path,
        },
    )

    # Post-scan side effects (alerts, etc.)
    try:
        log.info("post-scan alert jobs starting", extra={"run_id": run_id})
        post_scan_jobs(run_id)
        log.info("post-scan alert jobs finished", extra={"run_id": run_id})
    except Exception as e:
        log.exception("post-scan alert jobs failed", extra={"run_id": run_id, "error": str(e)})

    # Respond with helpful headers for clients (backfill/scheduler) to act on
    headers = {}
    if run_id:
        headers["X-Run-Id"] = str(run_id)
    if status:
        headers["X-Job-Status"] = str(status)
    if idempotency_key:
        headers["X-Idempotency-Key"] = str(idempotency_key)[:64]
    if rows_written is not None:
        headers["X-Rows-Written"] = str(rows_written)
    if snapshot_path:
        headers["X-Snapshot-Path"] = str(snapshot_path)

    return JSONResponse(
        status_code=http_status,
        headers=headers,
        content=result.model_dump(mode="json", exclude_none=True),
    )
