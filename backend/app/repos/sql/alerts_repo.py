# app/repos/sql/alerts_repo.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, date, timezone
from typing import Optional, Dict, Any

from sqlalchemy import (
    Column, Integer, String, DateTime, Date, JSON, Index, UniqueConstraint, func
)
from sqlalchemy.orm import Session, declarative_base

# Prefer shared Base if available; fallback to a local Base for migrations/tests.
try:
    from app.repos.models import Base  # type: ignore
except Exception:
    Base = declarative_base()


# -------------------- ORM MODELS --------------------
class AlertStateORM(Base):
    __tablename__ = "alert_state"
    id = Column(Integer, primary_key=True)
    symbol = Column(String(32), index=True, nullable=False)
    rule_code = Column(String(64), index=True, nullable=False)
    # store score as integer percent (e.g., 81 == 81.0)
    last_score = Column(Integer, nullable=True)
    last_fired_at_utc = Column(DateTime(timezone=True), nullable=True)
    last_fired_local_date = Column(Date, nullable=True)
    last_fired_run_id = Column(String(32), nullable=True)

    __table_args__ = (
        UniqueConstraint("symbol", "rule_code", name="uq_alertstate_symbol_rule"),
        Index("ix_alertstate_symbol_rule", "symbol", "rule_code"),
    )


class AlertEventORM(Base):
    __tablename__ = "alert_events"
    id = Column(Integer, primary_key=True)
    run_id = Column(String(32), index=True, nullable=False)
    symbol = Column(String(32), index=True, nullable=False)
    rule_code = Column(String(64), index=True, nullable=False)
    score = Column(Integer, nullable=True)
    channels_sent_json = Column(JSON, nullable=False, default={})
    created_at_utc = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("ix_alertevents_symbol_rule", "symbol", "rule_code"),
    )


# -------------------- DTO --------------------
@dataclass
class AlertState:
    symbol: str
    rule_code: str
    last_score: Optional[int] = None
    last_fired_at_utc: Optional[datetime] = None
    last_fired_local_date: Optional[date] = None
    last_fired_run_id: Optional[str] = None


# -------------------- REPO --------------------
class AlertsRepo:
    """
    SQLite repo for alert state + events.

    Methods are intentionally minimal to keep compatibility with existing UoW.
    """

    def __init__(self, session: Session):
        self.s = session

    # --- State ---
    def get_state(self, symbol: str, rule_code: str) -> AlertState:
        row = (
            self.s.query(AlertStateORM)
            .filter(AlertStateORM.symbol == symbol, AlertStateORM.rule_code == rule_code)
            .one_or_none()
        )
        if not row:
            return AlertState(symbol=symbol, rule_code=rule_code)
        return AlertState(
            symbol=row.symbol,
            rule_code=row.rule_code,
            last_score=row.last_score,
            last_fired_at_utc=row.last_fired_at_utc,
            last_fired_local_date=row.last_fired_local_date,
            last_fired_run_id=row.last_fired_run_id,
        )

    def upsert_state(
        self,
        symbol: str,
        rule_code: str,
        *,
        last_score: Optional[int],
        last_fired_at_utc: Optional[datetime],
        last_fired_local_date: Optional[date],
        last_fired_run_id: Optional[str],
    ) -> None:
        row = (
            self.s.query(AlertStateORM)
            .filter(AlertStateORM.symbol == symbol, AlertStateORM.rule_code == rule_code)
            .one_or_none()
        )
        if not row:
            row = AlertStateORM(symbol=symbol, rule_code=rule_code)
            self.s.add(row)
        row.last_score = last_score
        row.last_fired_at_utc = last_fired_at_utc
        row.last_fired_local_date = last_fired_local_date
        row.last_fired_run_id = last_fired_run_id

    # --- Events ---
    def log_event(
        self,
        *,
        run_id: str,
        symbol: str,
        rule_code: str,
        score: Optional[int],
        channels_sent: Dict[str, Any],
    ) -> None:
        evt = AlertEventORM(
            run_id=run_id,
            symbol=symbol,
            rule_code=rule_code,
            score=score,
            channels_sent_json=channels_sent,
            created_at_utc=datetime.now(timezone.utc),
        )
        self.s.add(evt)


# --------------- BACKWARD-COMPAT ALIAS ---------------
# Some parts of the codebase import SqlAlertsRepo from this module.
# Keep a direct alias so those imports continue to work without changes.
SqlAlertsRepo = AlertsRepo
