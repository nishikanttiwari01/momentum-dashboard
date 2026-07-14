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


class WealthGoal(Base):
    __tablename__ = "wealth_goals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    target_amount_inr: Mapped[float] = mapped_column(Float)
    deadline: Mapped[date] = mapped_column(Date)
    is_primary: Mapped[bool] = mapped_column(Boolean, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )


class WealthGoalScenario(Base):
    __tablename__ = "wealth_goal_scenarios"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    goal_id: Mapped[str] = mapped_column(ForeignKey("wealth_goals.id"), index=True)
    scenario_key: Mapped[str] = mapped_column(String(16))
    annual_return_pct: Mapped[float] = mapped_column(Float)
    monthly_contribution_inr: Mapped[float] = mapped_column(
        Float, default=0, server_default="0"
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
