from __future__ import annotations
from datetime import datetime
from sqlalchemy.orm import Session

from ..models import Job
from ..interfaces.base import IJobsRepo


class SqlJobsRepo(IJobsRepo):
    def __init__(self, session: Session):
        self.s = session

    def record_run(self, run_id: str, started_at: datetime) -> None:
        row = Job(
            name="screening",
            run_id=run_id,
            started_at=started_at,
            status="RUNNING",
            error=None,
        )
        self.s.add(row)

    def complete_run(
        self, run_id: str, ended_at: datetime, status: str, error: str | None = None
    )) -> None:
        row = (
            self.s.query(Job)
            .filter(Job.run_id == run_id)
            .order_by(Job.id.desc())
            .first()
        )
        if row is None:
            row = Job(name="screening", run_id=run_id, started_at=ended_at, status=status, error=error)
            self.s.add(row)
        row.ended_at = ended_at
        row.status = status
        row.error = error
