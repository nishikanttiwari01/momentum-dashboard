from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.schemas.runs import RunDetail, RunSummary, RunsList
from app.repos.sql.jobs_repo import SqlJobsRepo

# No prefix here; main.py mounts with its own prefix
router = APIRouter(tags=["Runs"])

@router.get("/runs", response_model=RunsList)
def list_runs(
    status: Optional[str] = Query(None, description="PENDING|RUNNING|SUCCEEDED|FAILED"),
    limit: int = Query(20, ge=1, le=200),
    s: Session = Depends(get_session),
):
    repo = SqlJobsRepo(s)
    rows = repo.list_recent(status=status, limit=limit)
    items = [
        RunSummary(
            run_id=r.run_id,
            status=r.status,
            started_at=r.started_at.replace(microsecond=0).isoformat() + "Z",
            finished_at=r.ended_at.replace(microsecond=0).isoformat() + "Z" if r.ended_at else None,
            rows_computed=None,
            duration_ms=None,
        )
        for r in rows
    ]
    return RunsList(items=items)

@router.get("/runs/{run_id}", response_model=RunDetail)
def get_run(run_id: str, s: Session = Depends(get_session)):
    repo = SqlJobsRepo(s)
    r = repo.get_by_run_id(run_id)
    if not r:
        raise HTTPException(status_code=404, detail="run not found")
    return RunDetail(
        run_id=r.run_id,
        status=r.status,
        started_at=r.started_at.replace(microsecond=0).isoformat() + "Z",
        finished_at=r.ended_at.replace(microsecond=0).isoformat() + "Z" if r.ended_at else None,
        rows_computed=None,
        duration_ms=None,
        key=getattr(r, "key", None),
        snapshot_path=None,
        as_of=None,
        error_json=None,
    )
