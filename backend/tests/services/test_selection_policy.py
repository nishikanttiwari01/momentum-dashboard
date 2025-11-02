from __future__ import annotations

from datetime import datetime, timezone

import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core import config as app_config
from app.repos.models import Base, Position
from app.repos.sql.positions_repo import PositionsRepo
from app.services.selection_service import apply_selection_policy


def _make_session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
    return SessionLocal(), engine


def test_selection_policy_prefers_highest_r_multiple():
    session, engine = _make_session()
    try:
        settings = app_config.load()
        strategy = settings.strategy
        policy = settings.selection_policy.model_copy(deep=True)
        policy.max_open_positions = 5
        policy.weekly_quota = 5
        policy.symbol_cooldown_days = 0
        policy.sector_cooldown_days = 0

        now_utc = datetime(2025, 1, 10, 9, 30, tzinfo=timezone.utc)
        trading_day = now_utc.date()

        rows = [
            {
                "symbol": "AAA.NS",
                "sector": "Energy",
                "buy_flag": True,
                "score": 82,
                "last": 100.0,
                "atr_pct": 4.0,
                "buy_profile": "swing_eod",
                "buy_mode": "EOD",
                "buy_reasons_inline": "Score 82; ATR 4%",
            },
            {
                "symbol": "BBB.NS",
                "sector": "Energy",
                "buy_flag": True,
                "score": 78,
                "last": 100.0,
                "atr_pct": 2.0,
                "buy_profile": "swing_eod",
                "buy_mode": "EOD",
                "buy_reasons_inline": "Score 78; ATR 2%",
            },
        ]

        result = apply_selection_policy(
            session=session,
            rows=rows,
            strategy=strategy,
            policy=policy,
            run_id="RUN_TEST",
            trading_day=trading_day,
            nifty_regime="UP",
            now_utc=now_utc,
        )

        assert result is not None
        assert result.symbol == "BBB.NS"
        assert result.row_index == 1
        assert result.r_multiple > 1.9  # higher R multiple candidate selected

        # Position should be persisted for the winner
        persisted = session.query(Position).all()
        assert len(persisted) == 1
        assert persisted[0].symbol == "BBB.NS"
        assert persisted[0].trade_on is True
    finally:
        session.close()
        engine.dispose()


def test_selection_policy_blocks_when_limits_hit():
    session, engine = _make_session()
    try:
        settings = app_config.load()
        strategy = settings.strategy
        policy = settings.selection_policy.model_copy(deep=True)
        policy.max_open_positions = 1
        policy.weekly_quota = 1
        policy.symbol_cooldown_days = 0
        policy.sector_cooldown_days = 0

        repo = PositionsRepo(session=session)
        repo.create_or_lock(symbol="HOLD.NS", price=120.0)

        now_utc = datetime(2025, 1, 10, 9, 30, tzinfo=timezone.utc)
        trading_day = now_utc.date()

        candidate_rows = [
            {
                "symbol": "NEW.NS",
                "sector": "IT",
                "buy_flag": True,
                "score": 88,
                "last": 150.0,
                "atr_pct": 3.0,
                "buy_profile": "swing_eod",
                "buy_mode": "EOD",
                "buy_reasons_inline": "Score 88; ATR 3%",
            }
        ]

        result = apply_selection_policy(
            session=session,
            rows=candidate_rows,
            strategy=strategy,
            policy=policy,
            run_id="RUN_LIMIT",
            trading_day=trading_day,
            nifty_regime="UP",
            now_utc=now_utc,
        )

        assert result is None
        # No additional positions created
        persisted = session.query(Position).filter(Position.symbol == "NEW.NS").count()
        assert persisted == 0
    finally:
        session.close()
        engine.dispose()
