# backend/app/api/v1/runs.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.repos.sql.jobs_repo import SqlJobsRepo
from app.schemas.runs import RunDetail, RunSummary, RunsList

router = APIRouter(tags=["Runs"])


def _tz_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensure datetime is timezone-aware (UTC). Leave None untouched."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


@router.get("/runs", response_model=RunsList)
def list_runs(
    status: Optional[str] = Query(None, description="PENDING|RUNNING|SUCCEEDED|FAILED"),
    limit: int = Query(20, ge=1, le=200),
    s: Session = Depends(get_session),
):
    """
    Returns an object with an 'items' array of RunSummary.
    Datetimes are returned as aware datetimes; FastAPI serializes to RFC3339.
    """
    repo = SqlJobsRepo(s)
    rows = repo.list_recent(status=status, limit=limit)

    items = [
        RunSummary(
            run_id=r.run_id,
            job_name=getattr(r, "name", None),
            started_at=_tz_aware(r.started_at),
            ended_at=_tz_aware(r.ended_at),
            status=r.status,  # "PENDING" | "RUNNING" | "SUCCEEDED" | "FAILED"
            duration_ms=getattr(r, "duration_ms", None),
            key=getattr(r, "key", None),
            snapshot_path=getattr(r, "snapshot_path", None),
        )
        for r in rows
    ]

    return RunsList(items=items)


@router.get("/runs/{run_id}", response_model=RunDetail)
def get_run(run_id: str, s: Session = Depends(get_session)):
    """
    Returns RunDetail with optional counts and error fields.
    """
    repo = SqlJobsRepo(s)
    r = repo.get_by_run_id(run_id)
    if not r:
        raise HTTPException(status_code=404, detail="run not found")

    sp = getattr(r, "symbols_processed", None)
    rw = getattr(r, "rows_written", None)
    counts_obj = {"symbols_processed": sp, "rows_written": rw} if (sp is not None or rw is not None) else None

    return RunDetail(
        run_id=r.run_id,
        job_name=getattr(r, "name", None),
        started_at=_tz_aware(r.started_at),
        ended_at=_tz_aware(r.ended_at),
        status=r.status,
        duration_ms=getattr(r, "duration_ms", None),
        key=getattr(r, "key", None),
        snapshot_path=getattr(r, "snapshot_path", None),
        counts=counts_obj,               # Pydantic will coerce dict -> Counts
        error=getattr(r, "error", None),
        error_json=getattr(r, "error_json", None),
    )
