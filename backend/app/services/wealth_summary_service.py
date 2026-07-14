from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.repos.models import PortfolioAsset, PortfolioSnapshot
from app.schemas.wealth_portfolio import FxMetadata, MarketExposure, WealthSummary
from app.services.wealth_fx_service import FxResult, get_usd_inr


class UnsupportedCurrency(ValueError):
    pass


def convert_to_inr(amount: float | None, currency: str, fx: FxResult | None) -> float | None:
    if amount is None:
        return None
    if currency == "INR":
        return amount
    if currency == "USD" and fx is not None:
        return amount * fx.rate
    raise UnsupportedCurrency(currency)


def build_summary(session: Session, fx: FxResult | None = None) -> WealthSummary:
    snapshot = session.scalar(
        select(PortfolioSnapshot)
        .order_by(PortfolioSnapshot.as_of.desc(), PortfolioSnapshot.created_at.desc())
        .limit(1)
    )
    if snapshot is None:
        return WealthSummary(data_health="empty")

    assets = list(session.scalars(select(PortfolioAsset).where(PortfolioAsset.snapshot_id == snapshot.id)))
    needs_usd = any(item.currency == "USD" for item in assets)
    if needs_usd and fx is None:
        fx = get_usd_inr(session, date.today())

    market_values: dict[str, float] = defaultdict(float)
    invested_total = 0.0
    market_total = 0.0
    for asset in assets:
        invested = convert_to_inr(asset.invested_amount, asset.currency, fx)
        value = convert_to_inr(asset.market_value, asset.currency, fx)
        invested_total += invested or 0.0
        market_total += value or 0.0
        market_values[asset.market] += value or 0.0

    exposure = [
        MarketExposure(
            market=market,
            market_value_inr=value,
            weight_pct=(value * 100 / market_total) if market_total else 0.0,
        )
        for market, value in sorted(market_values.items())
    ]
    fx_metadata = None
    if fx is not None:
        fx_metadata = FxMetadata(
            rate=fx.rate,
            effective_on=fx.effective_on,
            fetched_at=fx.fetched_at,
            source=fx.source,
            is_fallback=fx.is_fallback,
        )
    return WealthSummary(
        snapshot_id=snapshot.id,
        as_of=snapshot.as_of,
        net_worth_market_value_inr=market_total,
        invested_capital_inr=invested_total,
        investment_xirr_pct=None,
        market_exposure=exposure,
        fx=fx_metadata,
        data_health="warning" if fx and fx.is_fallback else "fresh",
    )
