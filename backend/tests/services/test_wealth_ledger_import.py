from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.db import dispose_engine, get_sessionmaker, init_sqlite
from app.repos.models import (
    WealthAsset,
    WealthAssetObservation,
    WealthCashFlow,
    WealthReportingPeriod,
    WealthReportingPeriodSource,
)
from app.services.wealth_import_service import WealthImportService
from tests.fixtures.wealth_workbook_factory import make_source_ledger_workbook_bytes


@pytest.fixture
def session(tmp_path: Path):
    dispose_engine()
    init_sqlite(str(tmp_path / "wealth-ledger.db"))
    db = get_sessionmaker()()
    try:
        yield db
    finally:
        db.close()
        dispose_engine()


def test_ledger_models_enforce_stable_fingerprint_uniqueness(session):
    first = WealthAsset(
        id="a1", source_key="stable", name="Asset", asset_class="financial",
        market="IN", currency="INR", source_ref={},
    )
    duplicate = WealthAsset(
        id="a2", source_key="stable", name="Asset", asset_class="financial",
        market="IN", currency="INR", source_ref={},
    )
    session.add_all([first, duplicate])
    with pytest.raises(IntegrityError):
        session.commit()


def test_import_persists_source_ledger_and_reporting_lineage(session):
    service = WealthImportService()
    payload = make_source_ledger_workbook_bytes()

    result = service.commit(session, service.preview(payload, "investment.xlsx").preview_token)

    assert result.created is True
    assert session.scalar(select(func.count()).select_from(WealthAsset)) == 4
    assert session.scalar(select(func.count()).select_from(WealthAssetObservation)) == 12
    assert session.scalar(select(func.count()).select_from(WealthCashFlow)) == 3
    assert session.scalar(select(func.count()).select_from(WealthReportingPeriod)) == 3
    assert session.scalar(select(func.count()).select_from(WealthReportingPeriodSource)) == 12
    source = session.scalar(select(WealthReportingPeriodSource).where(
        WealthReportingPeriodSource.metric == "property_market_value",
        WealthReportingPeriodSource.observed_on.is_not(None),
    ))
    assert source.source_sheet == "FIXED ASSET"
    assert source.source_cell in {"E4", "G4", "I4"}


def test_same_workbook_does_not_duplicate_ledger_facts(session):
    service = WealthImportService()
    payload = make_source_ledger_workbook_bytes()
    service.commit(session, service.preview(payload, "investment.xlsx").preview_token)

    result = service.commit(session, service.preview(payload, "renamed.xlsx").preview_token)

    assert result.created is False
    assert session.scalar(select(func.count()).select_from(WealthAssetObservation)) == 12
    assert session.scalar(select(func.count()).select_from(WealthCashFlow)) == 3
