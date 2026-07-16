from __future__ import annotations

from datetime import datetime, date
from typing import Optional, List

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Index,
    JSON,
    ForeignKey,
    func,
    MetaData,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# ---------- Alembic/SQLite-safe naming convention ----------
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=convention)


# ---------- Tables ----------

class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    rule_type: Mapped[str] = mapped_column(String(32))
    rule_value: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Use SQLite JSON1 (sa.JSON) for shape integrity. If portability is needed, switch to Text.
    channels: Mapped[List[str]] = mapped_column(JSON, default=list)

    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        # Composite index for most frequent access pattern
        Index("ix_alerts_symbol_enabled", "symbol", "enabled"),
    )


class Watchlist(Base):
    __tablename__ = "watchlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    note: Mapped[Optional[str]] = mapped_column(Text)


class History(Base):
    __tablename__ = "history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    as_of: Mapped[datetime] = mapped_column(DateTime, index=True)  # snapshot dt (UTC)
    outcome: Mapped[str] = mapped_column(String(32))
    pnl_pct: Mapped[Optional[float]] = mapped_column(Float)
    run_id: Mapped[Optional[str]] = mapped_column(String(20), index=True)
    meta_json: Mapped[Optional[str]] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("symbol", "as_of", name="uq_history_symbol_asof"),
        Index("ix_history_asof_symbol", "as_of", "symbol"),
    )


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), index=True)      # "screening", "digest"
    run_id: Mapped[str] = mapped_column(String(20), index=True)
    # NEW (Phase-9): idempotency support (nullable for backward compat)
    key: Mapped[Optional[str]] = mapped_column(String(64), unique=True, index=True, nullable=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(16), index=True)    # PENDING/RUNNING/SUCCEEDED/FAILED
    error: Mapped[Optional[str]] = mapped_column(Text)


class Setting(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # "app_yaml"
    value_yaml: Mapped[str] = mapped_column(Text)


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)

    # must be nullable for unlock
    entry_price_locked: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    qty: Mapped[Optional[int]] = mapped_column(Integer)
    stop_now: Mapped[Optional[float]] = mapped_column(Float)
    exit_close_threshold: Mapped[Optional[float]] = mapped_column(Float)
    breakeven_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    euphoria_on: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    trade_on: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    sell_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sold_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)

    __table_args__ = (
        Index("ix_positions_symbol_trade_on", "symbol", "trade_on"),
    )

    note: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(), nullable=False
    )



class SnapshotPin(Base):
    __tablename__ = "snapshot_pins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    run_id: Mapped[str] = mapped_column(String(20), index=True)


class CandidatePool(Base):
    __tablename__ = "candidate_pool"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True, index=True)

    added_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    added_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    added_run_id: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    added_as_of: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_seen_run_id: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    last_seen_as_of: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    last_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_adx14: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_atr_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_r_multiple: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_prox_52w_high_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_liquidity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_ema20: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    rank_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rank_ord: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)

    status: Mapped[str] = mapped_column(String(16), index=True, default="ACTIVE")
    exit_reason: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    removed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    removed_run_id: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    reasons_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_candidate_pool_status_rank", "status", "rank_ord"),
    )


class PortfolioImport(Base):
    __tablename__ = "portfolio_imports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    filename: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), index=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp(), nullable=False)
    issue_counts: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    import_id: Mapped[str] = mapped_column(ForeignKey("portfolio_imports.id"), unique=True, index=True)
    as_of: Mapped[date] = mapped_column(Date, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp(), nullable=False)


class PortfolioAsset(Base):
    __tablename__ = "portfolio_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("portfolio_snapshots.id"), index=True)
    source_key: Mapped[str] = mapped_column(String(64))
    asset_type: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(255))
    market: Mapped[str] = mapped_column(String(16), index=True)
    currency: Mapped[str] = mapped_column(String(3))
    invested_amount: Mapped[Optional[float]] = mapped_column(Float)
    market_value: Mapped[Optional[float]] = mapped_column(Float)
    source_ref: Mapped[dict] = mapped_column(JSON, nullable=False)

    __table_args__ = (UniqueConstraint("snapshot_id", "source_key"),)


class PortfolioTransaction(Base):
    __tablename__ = "portfolio_transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("portfolio_snapshots.id"), index=True)
    source_key: Mapped[str] = mapped_column(String(64))
    asset_id: Mapped[str] = mapped_column(ForeignKey("portfolio_assets.id"), index=True)
    occurred_on: Mapped[date] = mapped_column(Date, index=True)
    kind: Mapped[str] = mapped_column(String(16))
    amount: Mapped[float] = mapped_column(Float)
    units: Mapped[Optional[float]] = mapped_column(Float)
    unit_price: Mapped[Optional[float]] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3))
    source_ref: Mapped[dict] = mapped_column(JSON, nullable=False)

    __table_args__ = (UniqueConstraint("snapshot_id", "source_key"),)


class PortfolioValuation(Base):
    __tablename__ = "portfolio_valuations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("portfolio_snapshots.id"), index=True)
    source_key: Mapped[str] = mapped_column(String(64))
    asset_id: Mapped[str] = mapped_column(ForeignKey("portfolio_assets.id"), index=True)
    valued_on: Mapped[date] = mapped_column(Date, index=True)
    market_value: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3))
    source_ref: Mapped[dict] = mapped_column(JSON, nullable=False)

    __table_args__ = (UniqueConstraint("snapshot_id", "source_key"),)


class PortfolioFxRate(Base):
    __tablename__ = "portfolio_fx_rates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    base_currency: Mapped[str] = mapped_column(String(3))
    quote_currency: Mapped[str] = mapped_column(String(3))
    effective_on: Mapped[date] = mapped_column(Date)
    rate: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(64))
    fetched_at: Mapped[datetime] = mapped_column(DateTime)

    __table_args__ = (UniqueConstraint("base_currency", "quote_currency", "effective_on"),)


class PortfolioAnnualReviewOverride(Base):
    __tablename__ = "portfolio_annual_review_overrides"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    year: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    opening_net_worth_inr: Mapped[Optional[float]] = mapped_column(Float)
    contributions_inr: Mapped[Optional[float]] = mapped_column(Float)
    investment_gain_inr: Mapped[Optional[float]] = mapped_column(Float)
    property_gain_inr: Mapped[Optional[float]] = mapped_column(Float)
    rent_received_inr: Mapped[Optional[float]] = mapped_column(Float)
    withdrawals_inr: Mapped[Optional[float]] = mapped_column(Float)
    closing_net_worth_inr: Mapped[Optional[float]] = mapped_column(Float)
    investment_xirr_pct: Mapped[Optional[float]] = mapped_column(Float)
    notes: Mapped[Optional[str]] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp(), nullable=False)


class WealthAsset(Base):
    __tablename__ = "wealth_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    owner: Mapped[Optional[str]] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[Optional[str]] = mapped_column(String(120))
    asset_class: Mapped[str] = mapped_column(String(32), index=True)
    market: Mapped[str] = mapped_column(String(16))
    currency: Mapped[str] = mapped_column(String(3))
    source_ref: Mapped[dict] = mapped_column(JSON, nullable=False)


class WealthAssetObservation(Base):
    __tablename__ = "wealth_asset_observations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    import_id: Mapped[str] = mapped_column(ForeignKey("portfolio_imports.id"), index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("wealth_assets.id"), index=True)
    source_key: Mapped[str] = mapped_column(String(64), unique=True)
    observed_on: Mapped[date] = mapped_column(Date, index=True)
    principal: Mapped[Optional[float]] = mapped_column(Float)
    market_value: Mapped[Optional[float]] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3))
    source_ref: Mapped[dict] = mapped_column(JSON, nullable=False)


class WealthCashFlow(Base):
    __tablename__ = "wealth_cash_flows"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    import_id: Mapped[str] = mapped_column(ForeignKey("portfolio_imports.id"), index=True)
    asset_id: Mapped[Optional[str]] = mapped_column(ForeignKey("wealth_assets.id"), index=True)
    source_key: Mapped[str] = mapped_column(String(64), unique=True)
    occurred_on: Mapped[date] = mapped_column(Date, index=True)
    flow_type: Mapped[str] = mapped_column(String(32), index=True)
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3))
    source_ref: Mapped[dict] = mapped_column(JSON, nullable=False)


class WealthReportingPeriod(Base):
    __tablename__ = "wealth_reporting_periods"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    import_id: Mapped[str] = mapped_column(ForeignKey("portfolio_imports.id"), index=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    label: Mapped[str] = mapped_column(String(32))
    controls: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (UniqueConstraint("import_id", "year"),)


class WealthReportingPeriodSource(Base):
    __tablename__ = "wealth_reporting_period_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    period_id: Mapped[str] = mapped_column(ForeignKey("wealth_reporting_periods.id"), index=True)
    metric: Mapped[str] = mapped_column(String(40), index=True)
    source_sheet: Mapped[str] = mapped_column(String(64))
    source_cell: Mapped[str] = mapped_column(String(16))
    observed_on: Mapped[Optional[date]] = mapped_column(Date, index=True)

    __table_args__ = (UniqueConstraint("period_id", "metric"),)


class WealthGoal(Base):
    __tablename__ = "wealth_goals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    target_amount_inr: Mapped[float] = mapped_column(Float)
    deadline: Mapped[date] = mapped_column(Date)
    is_primary: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "uq_wealth_goals_primary",
            "is_primary",
            unique=True,
            sqlite_where=text("is_primary = 1"),
            postgresql_where=text("is_primary = true"),
        ),
    )


class FamilyWealthScenario(Base):
    __tablename__ = "wealth_goal_scenarios"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    goal_id: Mapped[str] = mapped_column(ForeignKey("wealth_goals.id"), index=True)
    scenario_key: Mapped[str] = mapped_column(String(16))
    annual_return_pct: Mapped[float] = mapped_column(Float)
    monthly_contribution_inr: Mapped[float] = mapped_column(
        Float, default=600000, server_default="600000"
    )
    property_growth_pct: Mapped[float] = mapped_column(
        Float, default=6, server_default="6"
    )
    step_up_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0"
    )
    step_up_pct: Mapped[float] = mapped_column(Float, default=6, server_default="6")
    contribution_stop_age: Mapped[int] = mapped_column(
        Integer, default=60, server_default="60"
    )
    display_order: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )

    __table_args__ = (UniqueConstraint("goal_id", "scenario_key"),)


# Preserve the established service/API import while the lifetime contract adopts
# the more precise family-specific name.
WealthGoalScenario = FamilyWealthScenario


class FamilyWealthPlan(Base):
    __tablename__ = "family_wealth_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    birth_year: Mapped[int] = mapped_column(Integer, default=1984, server_default="1984")
    birth_month: Mapped[int] = mapped_column(Integer, default=7, server_default="7")
    projection_end_age: Mapped[int] = mapped_column(
        Integer, default=80, server_default="80"
    )
    base_age: Mapped[int] = mapped_column(Integer)
    monthly_contribution_inr: Mapped[float] = mapped_column(Float)
    contribution_step_up_enabled: Mapped[bool] = mapped_column(Boolean)
    contribution_step_up_pct: Mapped[float] = mapped_column(Float)
    monthly_rent_inr: Mapped[float] = mapped_column(Float)
    rent_growth_pct: Mapped[float] = mapped_column(Float)
    reinvest_rent_until: Mapped[date] = mapped_column(Date)
    property_growth_pct: Mapped[float] = mapped_column(Float)
    withdrawal_rate_pct: Mapped[float] = mapped_column(Float)
    amber_margin_pct: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )


class FamilyWealthGoal(Base):
    __tablename__ = "family_wealth_goals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    plan_id: Mapped[str] = mapped_column(
        ForeignKey("family_wealth_plans.id"), index=True
    )
    goal_key: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(120))
    goal_type: Mapped[str] = mapped_column(String(24))
    current_value_amount_inr: Mapped[float] = mapped_column(Float)
    target_date: Mapped[date] = mapped_column(Date)
    inflation_pct: Mapped[float] = mapped_column(Float)
    funding_treatment: Mapped[str] = mapped_column(String(24))
    priority: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    display_order: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )

    __table_args__ = (UniqueConstraint("plan_id", "goal_key"),)
