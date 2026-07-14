from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.core.db import dispose_engine, get_sessionmaker, init_sqlite
from app.repos.models import PortfolioImport, PortfolioSnapshot
from app.services import wealth_import_service as module
from app.services.wealth_import_service import ImportBlocked, WealthImportService
from tests.fixtures.wealth_workbook_factory import make_workbook_bytes


@pytest.fixture
def session(tmp_path: Path):
    dispose_engine()
    init_sqlite(str(tmp_path / "wealth-import.db"))
    db = get_sessionmaker()()
    try:
        yield db
    finally:
        db.close()
        dispose_engine()


def test_same_fingerprint_returns_existing_snapshot(session):
    service = WealthImportService()
    payload = make_workbook_bytes()
    first = service.commit(session, service.preview(payload, "investment.xlsx").preview_token)
    second = service.commit(session, service.preview(payload, "renamed.xlsx").preview_token)
    assert first.snapshot_id == second.snapshot_id
    assert first.created is True
    assert second.created is False


def test_blocking_issue_writes_nothing(session):
    service = WealthImportService()
    preview = service.preview(make_workbook_bytes(invalid_transaction_date=True), "bad.xlsx")
    with pytest.raises(ImportBlocked):
        service.commit(session, preview.preview_token)
    assert session.scalar(select(func.count()).select_from(PortfolioSnapshot)) == 0


def test_insert_failure_rolls_back_import_and_snapshot(session, monkeypatch):
    service = WealthImportService()
    preview = service.preview(make_workbook_bytes(), "investment.xlsx")

    def fail(*args, **kwargs):
        raise RuntimeError("forced insert failure")

    monkeypatch.setattr(module, "_insert_transactions", fail)
    with pytest.raises(RuntimeError, match="forced insert failure"):
        service.commit(session, preview.preview_token)
    assert session.scalar(select(func.count()).select_from(PortfolioImport)) == 0
    assert session.scalar(select(func.count()).select_from(PortfolioSnapshot)) == 0
