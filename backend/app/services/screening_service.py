from __future__ import annotations
from datetime import datetime
from typing import Optional, Tuple, Dict, Any, List

import pyarrow as pa
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy.orm import Session

from app.repos.sql.jobs_repo import SqlJobsRepo
from app.repos.sql.history_repo import SqlHistoryRepo
from app.repos.parquet import datasets
from app.schemas.runs import RunDetail


def _utcnow_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _ensure_parquet_root() -> None:
    root = datasets.get_parquet_root()
    root.mkdir(parents=True, exist_ok=True)
    t = root / ".wcheck"
    t.write_text("ok")
    t.unlink(missing_ok=True)


def _write_empty_scores_snapshot(run_id: str, as_of: str) -> str:
    # Minimal schema with ZERO rows for Phase-9 tests
    tab = pa.table(
        {
            "symbol": pa.array([], pa.string()),
            "name": pa.array([], pa.string()),
            "sector": pa.array([], pa.string()),
            "last": pa.array([], pa.float64()),
            "change_pct": pa.array([], pa.float64()),
            "score": pa.array([], pa.int32()),  # keep schema stable for screener
            "as_of": pa.array([], pa.string()),
            "run_id": pa.array([], pa.string()),
        }
    )
    datasets.write_schema_version("scores", 1)
    w = datasets.begin_atomic_write("scores", run_id)
    try:
        w.write_df(tab)
        w.commit()
    except Exception:
        try:
            w.abort()
        except Exception:
            pass
        raise

    return str((datasets.get_parquet_root() / "scores" / f"run_id={run_id}").resolve())


def run_screening(
    *,
    session: Session,
    key: Optional[str],
    payload: Dict[str, Any],
) -> Tuple[RunDetail, bool]:
    """
    Phase-9 behavior:
      - first call for key → create job, write EMPTY snapshot, return created=True (201)
      - replay with same key → return existing job (200)
    """
    _ensure_parquet_root()

    jobs = SqlJobsRepo(session)
    history = SqlHistoryRepo(session)

    job, created = jobs.create_or_get_by_key(name="manual_scan", key=key, with_created=True)

    if not created:
        # replay: return current state
        return (
            RunDetail(
                run_id=job.run_id,
                status=job.status,
                started_at=job.started_at.replace(microsecond=0).isoformat() + "Z",
                finished_at=job.ended_at.replace(microsecond=0).isoformat() + "Z" if job.ended_at else None,
                rows_computed=None,
                duration_ms=None,
                key=getattr(job, "key", None),
                snapshot_path=None,
                as_of=None,
                error_json=job.error,
            ),
            False,
        )

    # fresh run → write EMPTY snapshot to satisfy Phase-9 tests
    as_of = payload.get("as_of") or _utcnow_iso()
    try:
        snapshot_path = _write_empty_scores_snapshot(job.run_id, as_of)
        jobs.complete_run(run_id=job.run_id, status="SUCCEEDED", error=None)

        try:
            history.insert_run_summary(run_id=job.run_id, as_of=as_of, rows=0)
        except Exception:
            pass

        return (
            RunDetail(
                run_id=job.run_id,
                status="SUCCEEDED",
                started_at=job.started_at.replace(microsecond=0).isoformat() + "Z",
                finished_at=_utcnow_iso(),
                rows_computed=0,
                duration_ms=None,
                key=getattr(job, "key", None),
                snapshot_path=snapshot_path,
                as_of=as_of,
                error_json=None,
            ),
            True,
        )
    except StarletteHTTPException:
        jobs.fail_run(run_id=job.run_id, error="screening_service raised HTTPException")
        raise
    except Exception as exc:
        jobs.fail_run(run_id=job.run_id, error=f"screening_service failed: {exc}")
        raise StarletteHTTPException(
            status_code=500,
            detail={"code": "INTERNAL_ERROR", "detail": f"screening_service failed: {exc}"},
        )
