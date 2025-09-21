# backend/app/repos/sql/jobs_repo.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Iterable, Tuple

from sqlalchemy.orm import Session

from app.repos.models import Job

RUN_ID_FMT = "%Y%m%d%H%M%S"


def _new_run_id() -> str:
    """Return a 14-char UTC timestamp, e.g. 20250921104512."""
    return datetime.now(timezone.utc).strftime(RUN_ID_FMT)


class SqlJobsRepo:
    """
    DB-backed Jobs repo with stable timestamp run_id and idempotency by (name,key).

    - create_or_get_by_key(name, key, with_created=False) -> Job | (Job, bool)
      * If a row exists for (name,key), returns it.
      * Else creates a new row with run_id=YYYYMMDDhhmmss and status=RUNNING.
      * When with_created=True, returns (job, created_flag).

    - record_run(run_id, name="screening", started_at=None)
      * Legacy helper to insert a row explicitly (RUNNING).

    - complete_run / fail_run update status and error fields.

    - get_by_run_id, list_recent, list_runs: convenience accessors.
    """

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
        Idempotent create: if (name,key) exists return it, else create RUNNING job.
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

        # Create new job with TIMESTAMP run_id (canonical)
        now = datetime.utcnow()
        run_id = _new_run_id()
        kwargs = dict(name=name, run_id=run_id, started_at=now, status="RUNNING")
        if supports_key:
            kwargs["key"] = key  # may be None

        row = Job(**kwargs)  # type: ignore[arg-type]
        self._session.add(row)
        self._session.flush()
        self._session.commit()  # visible to other sessions/requests
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

    # --- Legacy API kept as-is ---

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
        self._session.commit()
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
        self._session.commit()

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
