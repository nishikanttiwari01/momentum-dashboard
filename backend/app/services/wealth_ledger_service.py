from __future__ import annotations

from dataclasses import dataclass

from openpyxl.utils import column_index_from_string
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.repos.models import (
    PortfolioImport,
    WealthAsset,
    WealthAssetObservation,
    WealthCashFlow,
    WealthReportingPeriod,
    WealthReportingPeriodSource,
)


_CONTROL_LABELS = {
    "financial_principal": "current assests principal (year end)",
    "financial_market_value": "current assets market value (year end)",
    "property_principal": "fixed assests principal (year end)",
    "property_market_value": "fixed assests market value (year end)",
}


@dataclass(frozen=True)
class ReportingPeriodTotals:
    year: int
    label: str
    financial_principal: float | None
    financial_market_value: float | None
    property_principal: float | None
    property_market_value: float | None
    source_dates: dict[str, str]

    @property
    def total_principal(self) -> float | None:
        if self.financial_principal is None or self.property_principal is None:
            return None
        return self.financial_principal + self.property_principal

    @property
    def total_market_value(self) -> float | None:
        if self.financial_market_value is None or self.property_market_value is None:
            return None
        return self.financial_market_value + self.property_market_value


def _selected_total(session: Session, source: WealthReportingPeriodSource) -> float | None:
    if source.observed_on is None:
        return None
    asset_class = "property" if source.metric.startswith("property_") else "financial"
    observations = list(session.execute(
        select(WealthAssetObservation, WealthAsset).join(
            WealthAsset, WealthAsset.id == WealthAssetObservation.asset_id
        ).where(
            WealthAsset.asset_class == asset_class,
            WealthAssetObservation.observed_on == source.observed_on,
        )
    ))
    target_column = column_index_from_string("".join(filter(str.isalpha, source.source_cell)))
    value_name = "principal" if source.metric.endswith("principal") else "market_value"
    exact = [
        observation for observation, _ in observations
        if observation.source_ref.get("column") == target_column
        and getattr(observation, value_name) is not None
    ]
    selected = exact
    if not selected and value_name == "market_value":
        selected = [
            observation for observation, _ in observations
            if observation.source_ref.get("column") == target_column - 1
            and observation.market_value is not None
        ]
    if not selected:
        return None
    return sum(float(getattr(observation, value_name)) for observation in selected)


def get_reporting_period_totals(session: Session, year: int) -> ReportingPeriodTotals | None:
    period = session.scalar(
        select(WealthReportingPeriod)
        .join(PortfolioImport, PortfolioImport.id == WealthReportingPeriod.import_id)
        .where(WealthReportingPeriod.year == year)
        .order_by(PortfolioImport.imported_at.desc())
        .limit(1)
    )
    if period is None:
        return None
    sources = list(session.scalars(select(WealthReportingPeriodSource).where(
        WealthReportingPeriodSource.period_id == period.id
    )))
    values = {
        source.metric: (
            period.controls.get(_CONTROL_LABELS[source.metric])
            if period.controls.get(_CONTROL_LABELS[source.metric]) is not None
            else _selected_total(session, source)
        )
        for source in sources
    }
    return ReportingPeriodTotals(
        year=year,
        label=period.label,
        financial_principal=values.get("financial_principal"),
        financial_market_value=values.get("financial_market_value"),
        property_principal=values.get("property_principal"),
        property_market_value=values.get("property_market_value"),
        source_dates={
            source.metric: source.observed_on.isoformat()
            for source in sources if source.observed_on is not None
        },
    )


def property_capital_for_year(session: Session, year: int) -> float:
    return float(session.scalar(select(func.coalesce(func.sum(WealthCashFlow.amount), 0)).where(
        WealthCashFlow.flow_type == "property_capital",
        WealthCashFlow.occurred_on >= date(year, 1, 1),
        WealthCashFlow.occurred_on <= date(year, 12, 31),
    )) or 0)
