from datetime import date
from uuid import uuid4

from app.repos.models import (
    PortfolioAnnualReviewOverride,
    PortfolioAsset,
    PortfolioImport,
    PortfolioSnapshot,
    PortfolioTransaction,
)
from app.schemas.wealth_portfolio import AnnualReviewOverrideUpdate
from app.services.annual_review_service import (
    delete_annual_review_overrides,
    get_annual_review,
    save_annual_review_overrides,
)


def add_snapshot(session, as_of: date, suffix: str, financial: float, property_value: float):
    import_id, snapshot_id = str(uuid4()), str(uuid4())
    session.add(PortfolioImport(id=import_id, source_sha256=suffix * 64, filename=f"{suffix}.xlsx", status="SUCCEEDED", issue_counts={}))
    session.add(PortfolioSnapshot(id=snapshot_id, import_id=import_id, as_of=as_of))
    financial_id = str(uuid4())
    session.add_all([
        PortfolioAsset(id=financial_id, snapshot_id=snapshot_id, source_key=f"fund-{suffix}", asset_type="mutual_fund", name="Fund", market="IN", currency="INR", invested_amount=financial, market_value=financial, source_ref={}),
        PortfolioAsset(id=str(uuid4()), snapshot_id=snapshot_id, source_key=f"property-{suffix}", asset_type="property", name="Home", market="IN", currency="INR", invested_amount=property_value, market_value=property_value, source_ref={}),
    ])
    return snapshot_id, financial_id


def test_derives_snapshot_values_and_applies_only_manual_overrides(session):
    add_snapshot(session, date(2024, 12, 31), "a", 5_000_000, 3_000_000)
    snapshot_id, financial_id = add_snapshot(session, date(2025, 12, 31), "b", 6_200_000, 3_500_000)
    session.add(PortfolioTransaction(id=str(uuid4()), snapshot_id=snapshot_id, source_key="buy-1", asset_id=financial_id, occurred_on=date(2025, 6, 1), kind="buy", amount=500_000, units=None, unit_price=None, currency="INR", source_ref={}))
    session.commit()

    review = get_annual_review(session, 2025)
    assert review.opening_net_worth_inr.value == 8_000_000
    assert review.closing_net_worth_inr.value == 9_700_000
    assert review.contributions_inr.value == 500_000
    assert review.investment_gain_inr.value == 700_000
    assert review.property_gain_inr.value == 500_000
    assert review.rent_received_inr.value is None
    assert review.investment_xirr_pct.value is not None
    assert review.investment_xirr_pct.source == "calculated"
    assert review.reconciliation.status == "incomplete"

    saved = save_annual_review_overrides(session, 2025, AnnualReviewOverrideUpdate(rent_received_inr=120_000, investment_xirr_pct=12.5, notes="Verified"))
    assert saved.rent_received_inr.value == 120_000
    assert saved.rent_received_inr.source == "manual"
    assert saved.investment_xirr_pct.value == 12.5
    assert saved.notes == "Verified"

    restored = delete_annual_review_overrides(session, 2025)
    assert restored.rent_received_inr.value is None
    assert session.query(PortfolioAnnualReviewOverride).count() == 0


def test_missing_snapshots_remain_missing_instead_of_zero(session):
    review = get_annual_review(session, 2023)
    assert review.opening_net_worth_inr.value is None
    assert review.closing_net_worth_inr.value is None
    assert review.contributions_inr.value is None
    assert review.reconciliation.status == "incomplete"
