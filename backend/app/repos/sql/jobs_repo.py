from __future__ import annotations

from datetime import datetime
from typing import Optional, List, Dict, Any, Iterable, Tuple

from sqlalchemy.orm import Session

from app.repos.models import Job


class SqlJobsRepo:
    def __init__(self, session: Session):
        self._session = session

    def create_or_get_by_key(
        self,
        *,
        name: str,
        key: Optional[str],
        with_created: bool = False,
    ) -> Job | Tuple[Job, bool]:
        """
        Idempotent create: if (name,key) exists return it, else create a new RUNNING job.
        Back-compat:
          - Default returns Job (like before).
          - If with_created=True, returns (Job, created_flag).
        """
        supports_key = hasattr(Job, "key")

        if supports_key and key:
            existing = (
                self._session.query(Job)
                .filter(Job.name == name, Job.key == key)
                .order_by(Job.id.desc())
                .first()
            )
            if existing is not None:
                return (existing, False) if with_created else existing

        # create new
        now = datetime.utcnow()
        run_id = now.strftime("%Y%m%d%H%M%S")
        kwargs = dict(name=name, run_id=run_id, started_at=now, status="RUNNING")
        if supports_key:
            kwargs["key"] = key  # may be None

        row = Job(**kwargs)  # type: ignore[arg-type]
        self._session.add(row)
        self._session.flush()
        self._session.commit()  # <-- make visible to next request/session
        return (row, True) if with_created else row

    def get_by_run_id(self, run_id: str) -> Optional[Job]:
        return (
            self._session.query(Job)
            .filter(Job.run_id == run_id)
            .order_by(Job.id.desc())
            .first()
        )

    def list_recent(self, *, status: Optional[str] = None, limit: int = 20) -> Iterable[Job]:
        q = self._session.query(Job)
        if status:
            q = q.filter(Job.status == status)
        return q.order_by(Job.started_at.desc()).limit(int(limit)).all()

    # --- legacy API kept as-is, with commits added ---

    def record_run(
        self,
        run_id: str,
        *,
        name: str = "screening",
        started_at: Optional[datetime] = None,
    ) -> Job:
        row = Job(
            name=name,
            run_id=run_id,
            started_at=started_at or datetime.utcnow(),
            status="RUNNING",
        )
        self._session.add(row)
        self._session.flush()
        self._session.commit()  # ensure visibility
        return row

    def complete_run(
        self,
        run_id: str,
        *,
        ended_at: Optional[datetime] = None,
        status: str = "SUCCEEDED",
        error: Optional[str] = None,
    ) -> None:
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
        self._session.flush()
        self._session.commit()  # ensure visibility

    def fail_run(
        self,
        run_id: str,
        *,
        ended_at: Optional[datetime] = None,
        error: Optional[str] = None,
    ) -> None:
        self.complete_run(run_id, ended_at=ended_at, status="FAILED", error=error)

    def list_runs(self, name: Optional[str] = None) -> List[Dict[str, Any]]:
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


# Compatibility alias
JobsRepo = SqlJobsRepo
__all__ = ["SqlJobsRepo", "JobsRepo"]
