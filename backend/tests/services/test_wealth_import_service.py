from datetime import date
from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import load_workbook
from sqlalchemy import func, select

from app.core.db import dispose_engine, get_sessionmaker, init_sqlite
from app.repos.models import FamilyWealthPlan, PortfolioAsset, PortfolioImport, PortfolioSnapshot
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


def test_import_persists_reconciled_household_total_without_counting_fixed_components_twice(session):
    service = WealthImportService()
    result = service.commit(session, service.preview(make_workbook_bytes(include_household=True), "investment.xlsx").preview_token)
    assets = session.scalars(select(PortfolioAsset).where(PortfolioAsset.snapshot_id == result.snapshot_id)).all()
    assert sum(asset.market_value or 0 for asset in assets) == 83_058_852.25
    property_assets = [asset for asset in assets if asset.asset_type == "property"]
    assert len(property_assets) == 1
    assert property_assets[0].market_value == 38_400_000
    assert property_assets[0].source_ref["components"][0]["name"] == "Brigade land"


def test_reimport_preserves_later_app_plan_rent_override(session):
    service = WealthImportService()
    payload = make_workbook_bytes(include_household=True)
    service.commit(session, service.preview(payload, "investment.xlsx").preview_token)
    plan = FamilyWealthPlan(
        id="plan", base_age=50, monthly_contribution_inr=0,
        contribution_step_up_enabled=False, contribution_step_up_pct=0,
        monthly_rent_inr=55_000, rent_growth_pct=0,
        reinvest_rent_until=date(2030, 1, 1), property_growth_pct=0,
        withdrawal_rate_pct=4, amber_margin_pct=10,
    )
    session.add(plan)
    session.commit()
    workbook = load_workbook(BytesIO(payload))
    workbook["BALANCE SHEET"]["A1"] = "BALANCE SHEET (refreshed)"
    refreshed = BytesIO()
    workbook.save(refreshed)
    result = service.commit(session, service.preview(refreshed.getvalue(), "investment-refreshed.xlsx").preview_token)
    assert result.created is True
    assert session.get(FamilyWealthPlan, "plan").monthly_rent_inr == 55_000
