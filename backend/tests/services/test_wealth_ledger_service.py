from tests.fixtures.wealth_workbook_factory import make_source_ledger_workbook_bytes

from app.services.wealth_import_service import WealthImportService
from app.services.wealth_ledger_service import get_reporting_period_totals


def test_resolves_reporting_period_to_selected_source_columns(session):
    service = WealthImportService()
    payload = make_source_ledger_workbook_bytes()
    service.commit(session, service.preview(payload, "investment.xlsx").preview_token)

    totals = get_reporting_period_totals(session, 2026)

    assert totals.label == "FY-2026"
    assert totals.financial_principal == 1_610_000
    assert totals.financial_market_value == 1_840_000
    assert totals.property_principal == 14_500_000
    assert totals.property_market_value == 29_000_000
    assert totals.source_dates == {
        "financial_principal": "2026-04-25",
        "financial_market_value": "2026-04-25",
        "property_principal": "2026-04-25",
        "property_market_value": "2026-04-25",
    }


def test_returns_none_when_reporting_period_is_absent(session):
    assert get_reporting_period_totals(session, 2020) is None
