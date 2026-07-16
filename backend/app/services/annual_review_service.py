from __future__ import annotations

from datetime import date
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.repos.models import PortfolioAnnualReviewOverride, PortfolioAsset, PortfolioFxRate, PortfolioSnapshot, PortfolioTransaction, WealthReportingPeriod
from app.schemas.wealth_portfolio import AnnualReviewField, AnnualReviewOverrideUpdate, AnnualReviewReconciliation, AnnualReviewResponse
from app.services.portfolio_service import xirr
from app.services.wealth_ledger_service import get_reporting_period_totals, property_capital_for_year

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


def _inr_value(session: Session, amount: float | None, currency: str, on: date) -> float | None:
    if amount is None:
        return 0.0
    if currency == "INR":
        return amount
    if currency != "USD":
        return None
    rate = session.scalar(
        select(PortfolioFxRate.rate).where(
            PortfolioFxRate.base_currency == "USD",
            PortfolioFxRate.quote_currency == "INR",
            PortfolioFxRate.effective_on <= on,
        ).order_by(PortfolioFxRate.effective_on.desc()).limit(1)
    )
    return amount * rate if rate is not None else None


def _totals(session: Session, snapshot: PortfolioSnapshot | None) -> tuple[float | None, float | None]:
    if snapshot is None:
        return None, None
    assets = list(session.scalars(select(PortfolioAsset).where(PortfolioAsset.snapshot_id == snapshot.id)))
    converted = [(asset, _inr_value(session, asset.market_value, asset.currency, snapshot.as_of)) for asset in assets]
    if any(value is None for _, value in converted):
        return None, None
    financial = sum(value or 0 for asset, value in converted if asset.asset_type not in PROPERTY_TYPES)
    property_value = sum(value or 0 for asset, value in converted if asset.asset_type in PROPERTY_TYPES)
    return financial, property_value


def _flows(session: Session, snapshot: PortfolioSnapshot | None, year: int) -> tuple[float | None, float | None, list[tuple[date, str, float]]]:
    if snapshot is None:
        return None, None, []
    rows = list(session.scalars(select(PortfolioTransaction).where(
        PortfolioTransaction.snapshot_id == snapshot.id,
        PortfolioTransaction.occurred_on >= date(year, 1, 1),
        PortfolioTransaction.occurred_on <= date(year, 12, 31),
    )))
    converted = [(row, _inr_value(session, row.amount, row.currency, row.occurred_on)) for row in rows]
    if any(value is None for _, value in converted):
        return None, None, []
    buys = sum(value or 0 for row, value in converted if row.kind.lower() in {"buy", "contribution", "invest"})
    sells = sum(abs(value or 0) for row, value in converted if row.kind.lower() in {"sell", "withdrawal", "redeem"})
    return buys, sells, [(row.occurred_on, row.kind.lower(), float(value)) for row, value in converted if value is not None]


def _field(calculated: float | None, source: str, explanation: str, override: float | None) -> AnnualReviewField:
    if override is not None:
        return AnnualReviewField(value=override, calculated_value=calculated, source="manual", explanation="Manual override")
    return AnnualReviewField(value=calculated, calculated_value=calculated, source=source if calculated is not None else "missing", explanation=explanation)


def get_annual_review(session: Session, year: int) -> AnnualReviewResponse:
    ledger_opening = get_reporting_period_totals(session, year - 1)
    ledger_closing = get_reporting_period_totals(session, year)
    opening = _snapshot_on_or_before(session, date(year - 1, 12, 31))
    closing = _snapshot_on_or_before(session, date(year, 12, 31), within_year=year)
    use_ledger = ledger_closing is not None
    if use_ledger:
        open_financial = ledger_opening.financial_market_value if ledger_opening else None
        open_property = ledger_opening.property_market_value if ledger_opening else None
        close_financial = ledger_closing.financial_market_value
        close_property = ledger_closing.property_market_value
        if ledger_opening and all(value is not None for value in (
            ledger_opening.financial_principal, ledger_opening.property_principal,
            ledger_closing.financial_principal, ledger_closing.property_principal,
        )):
            financial_net = ledger_closing.financial_principal - ledger_opening.financial_principal
            property_capital = property_capital_for_year(session, year)
            contributions = max(financial_net, 0) + property_capital
            withdrawals = max(-financial_net, 0)
            investment_gain = None if open_financial is None or close_financial is None else close_financial - open_financial - contributions + withdrawals
            property_gain = None if open_property is None or close_property is None else close_property - open_property
        else:
            contributions = withdrawals = investment_gain = property_gain = None
        transactions = []
    else:
        open_financial, open_property = _totals(session, opening)
        close_financial, close_property = _totals(session, closing)
        contributions, withdrawals, transactions = _flows(session, closing, year)
        property_gain = None if open_property is None or close_property is None else close_property - open_property
        investment_gain = None if open_financial is None or close_financial is None or contributions is None or withdrawals is None else close_financial - open_financial - contributions + withdrawals
    opening_total = None if open_financial is None or open_property is None else open_financial + open_property
    closing_total = None if close_financial is None or close_property is None else close_financial + close_property
    investment_xirr = None
    if not use_ledger and open_financial is not None and close_financial is not None:
        cashflows = [(date(year, 1, 1), -open_financial)]
        for occurred_on, kind, amount_inr in transactions:
            if kind in {"buy", "contribution", "invest"}:
                cashflows.append((occurred_on, -abs(amount_inr)))
            elif kind in {"sell", "withdrawal", "redeem"}:
                cashflows.append((occurred_on, abs(amount_inr)))
        cashflows.append((date(year, 12, 31), close_financial))
        investment_xirr = xirr(cashflows)
    override = session.scalar(select(PortfolioAnnualReviewOverride).where(PortfolioAnnualReviewOverride.year == year))
    source_label = "workbook source ledger" if use_ledger else "portfolio snapshot"
    values = {
        "opening_net_worth_inr": (opening_total, "imported", f"Opening {source_label}"),
        "contributions_inr": (contributions, "calculated", "Change in source principal" if use_ledger else "Dated investment transactions"),
        "investment_gain_inr": (investment_gain, "calculated", "Financial market movement after principal change"),
        "property_gain_inr": (property_gain, "calculated", "Property market movement after principal change"),
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
    opening_date = max(ledger_opening.source_dates.values()) if ledger_opening and ledger_opening.source_dates else (opening.as_of if opening else None)
    closing_date = max(ledger_closing.source_dates.values()) if ledger_closing and ledger_closing.source_dates else (closing.as_of if closing else None)
    return AnnualReviewResponse(
        year=year, opening_snapshot_date=opening_date, closing_snapshot_date=closing_date,
        reporting_label=ledger_closing.label if ledger_closing else None,
        selection_method="workbook_formula_lineage" if use_ledger else "legacy_snapshot",
        source_dates=ledger_closing.source_dates if ledger_closing else {},
        reconciliation=reconciliation, notes=override.notes if override else None, **fields,
    )


def list_annual_reviews(session: Session) -> list[AnnualReviewResponse]:
    years = {item.as_of.year for item in session.scalars(select(PortfolioSnapshot))}
    years.update(session.scalars(select(WealthReportingPeriod.year)))
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
