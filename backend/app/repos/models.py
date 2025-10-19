from __future__ import annotations

from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Index,
    JSON,
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
