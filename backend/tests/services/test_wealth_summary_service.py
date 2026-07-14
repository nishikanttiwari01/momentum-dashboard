from datetime import date, datetime
from uuid import uuid4

from app.repos.models import PortfolioAsset, PortfolioImport, PortfolioSnapshot
from app.services.wealth_fx_service import FxResult
from app.services.wealth_summary_service import build_summary


def test_summary_converts_usd_and_includes_property(session):
    import_id, snapshot_id = str(uuid4()), str(uuid4())
    session.add(PortfolioImport(id=import_id, source_sha256="b" * 64, filename="investment.xlsx", status="SUCCEEDED", issue_counts={}))
    session.add(PortfolioSnapshot(id=snapshot_id, import_id=import_id, as_of=date(2026, 7, 14)))
    session.add_all([
        PortfolioAsset(id=str(uuid4()), snapshot_id=snapshot_id, source_key="mf", asset_type="mutual_fund", name="Indian MF", market="IN", currency="INR", invested_amount=400000, market_value=520000, source_ref={}),
        PortfolioAsset(id=str(uuid4()), snapshot_id=snapshot_id, source_key="qqq", asset_type="etf", name="QQQ", market="US", currency="USD", invested_amount=1000, market_value=1200, source_ref={}),
        PortfolioAsset(id=str(uuid4()), snapshot_id=snapshot_id, source_key="office", asset_type="property", name="Office", market="IN", currency="INR", invested_amount=5000000, market_value=6500000, source_ref={}),
    ])
    session.commit()
    summary = build_summary(session, fx=FxResult(rate=86.25, effective_on=date(2026, 7, 14), source="test", fetched_at=datetime(2026, 7, 14), is_fallback=False))
    assert summary.net_worth_market_value_inr == 520000 + 1200 * 86.25 + 6500000
    assert summary.invested_capital_inr == 400000 + 1000 * 86.25 + 5000000
    assert {item.market for item in summary.market_exposure} == {"IN", "US"}


def test_summary_is_empty_before_first_snapshot(session):
    assert build_summary(session).data_health == "empty"
