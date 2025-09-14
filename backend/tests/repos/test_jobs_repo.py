from __future__ import annotations

from app.core.db import get_sessionmaker
from app.repos.sql.jobs_repo import SqlJobsRepo, JobsRepo  # alias must resolve

def test_jobs_repo_create_or_get_by_key_is_idempotent():
    sm = get_sessionmaker()
    with sm() as s:
        repo = SqlJobsRepo(s)
        a = repo.create_or_get_by_key(name="manual_scan", key="DEDUP1")
        b = repo.create_or_get_by_key(name="manual_scan", key="DEDUP1")
        assert a.id == b.id
        assert a.run_id == b.run_id

def test_jobs_repo_list_and_get_by_run_id():
    sm = get_sessionmaker()
    with sm() as s:
        repo = JobsRepo(s)  # compatibility alias
        row = repo.create_or_get_by_key(name="manual_scan", key="LIST1")
        got = repo.get_by_run_id(row.run_id)
        assert got is not None
        rows = list(repo.list_recent(limit=10))
        assert any(r.run_id == row.run_id for r in rows)
