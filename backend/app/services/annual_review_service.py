from __future__ import annotations

from datetime import date
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.repos.models import PortfolioAnnualReviewOverride, PortfolioAsset, PortfolioSnapshot, PortfolioTransaction
from app.schemas.wealth_portfolio import AnnualReviewField, AnnualReviewOverrideUpdate, AnnualReviewReconciliation, AnnualReviewResponse
from app.services.portfolio_service import xirr

PROPERTY_TYPES = {"property", "real_estate"}
OVERRIDE_FIELDS = (
    "opening_net_worth_inr", "contributions_inr", "investment_gain_inr", "property_gain_inr",
    "rent_received_inr", "withdrawals_inr", "closing_net_worth_inr", "investment_xirr_pct",
)


def _snapshot_on_or_before(session: Session, on: date, *, within_year: int | None = None) -> PortfolioSnapshot | None:
    query = select(PortfolioSnapshot).where(PortfolioSnapshot.as_of <= on)
    if within_year is not None:
        query = query.where(PortfolioSnapshot.as_of >= date(within_year, 1, 1))
    return session.scalar(query.order_by(PortfolioSnapshot.as_of.desc(), PortfolioSnapshot.created_at.desc()).limit(1))


def _totals(session: Session, snapshot: PortfolioSnapshot | None) -> tuple[float | None, float | None]:
    if snapshot is None:
        return None, None
    assets = list(session.scalars(select(PortfolioAsset).where(PortfolioAsset.snapshot_id == snapshot.id)))
    if any(asset.currency != "INR" and asset.market_value is not None for asset in assets):
        return None, None
    financial = sum((asset.market_value or 0) for asset in assets if asset.asset_type not in PROPERTY_TYPES)
    property_value = sum((asset.market_value or 0) for asset in assets if asset.asset_type in PROPERTY_TYPES)
    return financial, property_value


def _flows(session: Session, snapshot: PortfolioSnapshot | None, year: int) -> tuple[float | None, float | None, list[PortfolioTransaction]]:
    if snapshot is None:
        return None, None, []
    rows = list(session.scalars(select(PortfolioTransaction).where(
        PortfolioTransaction.snapshot_id == snapshot.id,
        PortfolioTransaction.occurred_on >= date(year, 1, 1),
        PortfolioTransaction.occurred_on <= date(year, 12, 31),
    )))
    if any(row.currency != "INR" for row in rows):
        return None, None, []
    buys = sum(row.amount for row in rows if row.kind.lower() in {"buy", "contribution", "invest"})
    sells = sum(abs(row.amount) for row in rows if row.kind.lower() in {"sell", "withdrawal", "redeem"})
    return buys, sells, rows


def _field(calculated: float | None, source: str, explanation: str, override: float | None) -> AnnualReviewField:
    if override is not None:
        return AnnualReviewField(value=override, calculated_value=calculated, source="manual", explanation="Manual override")
    return AnnualReviewField(value=calculated, calculated_value=calculated, source=source if calculated is not None else "missing", explanation=explanation)


def get_annual_review(session: Session, year: int) -> AnnualReviewResponse:
    opening = _snapshot_on_or_before(session, date(year - 1, 12, 31))
    closing = _snapshot_on_or_before(session, date(year, 12, 31), within_year=year)
    open_financial, open_property = _totals(session, opening)
    close_financial, close_property = _totals(session, closing)
    contributions, withdrawals, transactions = _flows(session, closing, year)
    opening_total = None if open_financial is None or open_property is None else open_financial + open_property
    closing_total = None if close_financial is None or close_property is None else close_financial + close_property
    property_gain = None if open_property is None or close_property is None else close_property - open_property
    investment_gain = None if open_financial is None or close_financial is None or contributions is None or withdrawals is None else close_financial - open_financial - contributions + withdrawals
    investment_xirr = None
    if open_financial is not None and close_financial is not None:
        cashflows = [(date(year, 1, 1), -open_financial)]
        for transaction in transactions:
            if transaction.kind.lower() in {"buy", "contribution", "invest"}:
                cashflows.append((transaction.occurred_on, -abs(transaction.amount)))
            elif transaction.kind.lower() in {"sell", "withdrawal", "redeem"}:
                cashflows.append((transaction.occurred_on, abs(transaction.amount)))
        cashflows.append((date(year, 12, 31), close_financial))
        investment_xirr = xirr(cashflows)
    override = session.scalar(select(PortfolioAnnualReviewOverride).where(PortfolioAnnualReviewOverride.year == year))
    values = {
        "opening_net_worth_inr": (opening_total, "imported", "Opening portfolio snapshot"),
        "contributions_inr": (contributions, "calculated", "Dated investment transactions"),
        "investment_gain_inr": (investment_gain, "calculated", "Financial value movement after net flows"),
        "property_gain_inr": (property_gain, "calculated", "Property snapshot value movement"),
        "rent_received_inr": (None, "missing", "No actual rental receipts are stored"),
        "withdrawals_inr": (withdrawals, "calculated", "Dated sell and withdrawal transactions"),
        "closing_net_worth_inr": (closing_total, "imported", "Closing portfolio snapshot"),
        "investment_xirr_pct": (investment_xirr, "calculated", "Annual dated financial cash flows and ending value"),
    }
    fields = {name: _field(calc, source, explanation, getattr(override, name) if override else None) for name, (calc, source, explanation) in values.items()}
    required = [fields[name].value for name in ("opening_net_worth_inr", "contributions_inr", "investment_gain_inr", "property_gain_inr", "rent_received_inr", "withdrawals_inr", "closing_net_worth_inr")]
    if any(value is None for value in required):
        reconciliation = AnnualReviewReconciliation(status="incomplete")
    else:
        opening_value, contribution_value, investment_value, property_value, rent_value, withdrawal_value, closing_value = required
        expected = opening_value + contribution_value + investment_value + property_value + rent_value - withdrawal_value
        difference = closing_value - expected
        reconciliation = AnnualReviewReconciliation(status="reconciled" if abs(difference) <= 1000 else "needs_review", expected_closing_inr=expected, difference_inr=difference)
    return AnnualReviewResponse(year=year, opening_snapshot_date=opening.as_of if opening else None, closing_snapshot_date=closing.as_of if closing else None, reconciliation=reconciliation, notes=override.notes if override else None, **fields)


def list_annual_reviews(session: Session) -> list[AnnualReviewResponse]:
    years = {item.as_of.year for item in session.scalars(select(PortfolioSnapshot))}
    years.update(session.scalars(select(PortfolioAnnualReviewOverride.year)))
    return [get_annual_review(session, year) for year in sorted(years, reverse=True)]


def save_annual_review_overrides(session: Session, year: int, payload: AnnualReviewOverrideUpdate) -> AnnualReviewResponse:
    row = session.scalar(select(PortfolioAnnualReviewOverride).where(PortfolioAnnualReviewOverride.year == year))
    if row is None:
        row = PortfolioAnnualReviewOverride(id=str(uuid4()), year=year)
        session.add(row)
    for name, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, name, value)
    session.commit()
    return get_annual_review(session, year)


def delete_annual_review_overrides(session: Session, year: int) -> AnnualReviewResponse:
    row = session.scalar(select(PortfolioAnnualReviewOverride).where(PortfolioAnnualReviewOverride.year == year))
    if row is not None:
        session.delete(row)
        session.commit()
    return get_annual_review(session, year)
