from __future__ import annotations

from datetime import datetime, timedelta, timezone, date

import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.alerts.types import Mode
from app.core import config as app_config
from app.repos.models import Base, Position
from app.repos.sql.positions_repo import PositionsRepo
from app.services.sell_engine import evaluate_positions


def _make_session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
    return SessionLocal(), engine


def test_sell_engine_prefers_timeout_over_targets():
    session, engine = _make_session()
    try:
        repo = PositionsRepo(session=session)
        pos = repo.create_or_lock(symbol="EXIT.NS", price=100.0)

        trading_day = date(2025, 2, 1)
        old_created_at = datetime(2025, 1, 1, 9, 15, tzinfo=timezone.utc)
        session.query(Position).filter(Position.id == pos["id"]).update(
            {
                "created_at": old_created_at.replace(tzinfo=None),
                "stop_now": 95.0,
                "breakeven_active": False,
            }
        )
        session.commit()

        rows_by_symbol = {
            "EXIT.NS": {
                "symbol": "EXIT.NS",
                "last": 120.0,
                "score": 85.0,
                "n_consecutive_down": 3,
                "relvol20": 1.5,
                "pivot_high_20": 110.0,
                "run_id": "RUN_TIMEOUT",
                "as_of": "2025-02-01T15:30:00Z",
                "buy_profile": "swing_eod",
                "buy_mode": "EOD",
                "buy_reasons_inline": "High momentum",
                "ema10": 130.0,
            }
        }
        frames_by_symbol = {"EXIT.NS": (None, None)}

        settings = app_config.load()
        events = evaluate_positions(
            session=session,
            rows_by_symbol=rows_by_symbol,
            frames_by_symbol=frames_by_symbol,
            strategy=settings.strategy,
            mode=Mode.EOD,
            trading_day=trading_day,
            now_utc=datetime(2025, 2, 1, 10, 0, tzinfo=timezone.utc),
        )

        assert [evt.event_code for evt in events] == ["SELL_TIMEOUT"]
        assert events[0].context["symbol"] == "EXIT.NS"
        assert events[0].context["days_since_entry"] >= 20
    finally:
        session.close()
        engine.dispose()
