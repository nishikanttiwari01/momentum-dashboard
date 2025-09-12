from __future__ import annotations

from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy.orm import Session

from app.repos.models import Job


class SqlJobsRepo:
    def __init__(self, session: Session):
        self._session = session

    def record_run(
        self,
        run_id: str,
        *,
        name: str = "screening",
        started_at: Optional[datetime] = None,
    ) -> Job:
        """Create a RUNNING job row."""
        row = Job(
            name=name,
            run_id=run_id,
            started_at=started_at or datetime.utcnow(),
            status="RUNNING",
        )
        self._session.add(row)
        # Flush to populate row.id without committing the transaction yet
        self._session.flush()
        return row

    def complete_run(
        self,
        run_id: str,
        *,
        ended_at: Optional[datetime] = None,
        status: str = "SUCCEEDED",
        error: Optional[str] = None,
    ) -> None:
        """
        Mark the most recent job with this run_id as completed.
        Default status = SUCCEEDED; pass status="FAILED" to mark failure.
        """
        row: Optional[Job] = (
            self._session.query(Job)
            .filter(Job.run_id == run_id)
            .order_by(Job.id.desc())
            .first()
        )
        if row is None:
            raise ValueError(f"No job found for run_id={run_id}")

        row.ended_at = ended_at or datetime.utcnow()
        row.status = status
        row.error = error
        # No commit here; UnitOfWork will commit/rollback the transaction.

    def fail_run(
        self,
        run_id: str,
        *,
        ended_at: Optional[datetime] = None,
        error: Optional[str] = None,
    ) -> None:
        """Convenience: mark job as FAILED."""
        self.complete_run(run_id, ended_at=ended_at, status="FAILED", error=error)

    def list_runs(self, name: Optional[str] = None) -> List[Dict[str, Any]]:
        """List jobs, newest first. Optional filter by name."""
        q = self._session.query(Job)
        if name:
            q = q.filter(Job.name == name)
        rows = q.order_by(Job.started_at.desc()).all()
        return [
            {
                "id": r.id,
                "name": r.name,
                "run_id": r.run_id,
                "status": r.status,
                "started_at": r.started_at,
                "ended_at": r.ended_at,
                "error": r.error,
            }
            for r in rows
        ]
