from __future__ import annotations

from datetime import datetime, timedelta, timezone, date

import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import create_engine, text

from app.alerts.router import route_event
from app.alerts.types import Mode
from app.core.config import (
    AlertDeliveryConfig,
    AlertDeliveryEmailConfig,
    AlertDeliveryNtfyConfig,
    AlertEmailTemplate,
    AlertRouteConfig,
    AlertThrottleConfig,
    AlertThrottleDefaultsConfig,
    AlertTemplatesConfig,
    AlertTopicConfig,
    AlertsRoutingConfig,
)
from app.repos.models import Base


def _make_connection():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return engine, engine.connect()


def test_route_event_respects_symbol_and_event_throttles():
    engine, conn = _make_connection()
    try:
        cfg = AlertsRoutingConfig(
            version=3,
            metadata={"timezone": "Asia/Kolkata"},
            delivery=AlertDeliveryConfig(
                email=AlertDeliveryEmailConfig(enabled=False),
                ntfy=AlertDeliveryNtfyConfig(enabled=False),
            ),
            topics={"high_signal": AlertTopicConfig(channels=["email"])},
            routes={
                "TEST_EVT": AlertRouteConfig(
                    enabled=True,
                    topic="high_signal",
                    throttle=AlertThrottleConfig(
                        per_symbol_cooldown_min=15,
                        per_event_cooldown_min=60,
                    ),
                )
            },
            templates=AlertTemplatesConfig(
                ntfy={"TEST_EVT": "NTFY {{symbol}}"},
                email={"TEST_EVT": AlertEmailTemplate(subject="Subject {{symbol}}", body="Body {{description}}")},
            ),
            throttle_defaults=AlertThrottleDefaultsConfig(),
        )

        base_time = datetime(2025, 1, 1, 3, 0, tzinfo=timezone.utc)
        trading_day = date(2025, 1, 1)

        first = route_event(
            conn,
            alerts_cfg=cfg,
            event_code="TEST_EVT",
            symbol="AAA.NS",
            mode=Mode.EOD,
            trading_date=trading_day,
            now_utc=base_time,
            context={"symbol": "AAA.NS", "description": "first"},
            score_at_fire=None,
            next_action_code=None,
        )
        assert first is not None

        blocked_same_symbol = route_event(
            conn,
            alerts_cfg=cfg,
            event_code="TEST_EVT",
            symbol="AAA.NS",
            mode=Mode.EOD,
            trading_date=trading_day,
            now_utc=base_time + timedelta(minutes=10),
            context={"symbol": "AAA.NS", "description": "too soon symbol"},
            score_at_fire=None,
            next_action_code=None,
        )
        assert blocked_same_symbol is None

        blocked_same_event = route_event(
            conn,
            alerts_cfg=cfg,
            event_code="TEST_EVT",
            symbol="BBB.NS",
            mode=Mode.EOD,
            trading_date=trading_day,
            now_utc=base_time + timedelta(minutes=10),
            context={"symbol": "BBB.NS", "description": "event cooldown"},
            score_at_fire=None,
            next_action_code=None,
        )
        assert blocked_same_event is None

        allowed_after_cooldown = route_event(
            conn,
            alerts_cfg=cfg,
            event_code="TEST_EVT",
            symbol="BBB.NS",
            mode=Mode.EOD,
            trading_date=trading_day,
            now_utc=base_time + timedelta(minutes=70),
            context={"symbol": "BBB.NS", "description": "late ok"},
            score_at_fire=77.0,
            next_action_code="NEXT",
        )
        assert allowed_after_cooldown is not None
        assert allowed_after_cooldown != first

        # Ensure event-level state row was recorded
        count_all = conn.execute(
            text("SELECT COUNT(1) FROM alert_state WHERE symbol='__ALL__' AND rule_code='TEST_EVT'")
        ).scalar_one()
        assert count_all == 1
    finally:
        conn.close()
        engine.dispose()
