from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.alerts import router
from app.alerts.types import Mode
from app.core import config as app_config

logger = logging.getLogger(__name__)


def route_event(
    session: Session,
    *,
    event_code: str,
    symbol: str,
    mode: Mode,
    trading_date: date,
    context: Dict[str, Any],
    score_at_fire: Optional[float] = None,
    next_action_code: Optional[str] = None,
) -> Optional[int]:
    """
    Route a structured alert event using the configured routing rules.
    """
    alerts_cfg = getattr(app_config.get_settings(), "alerts", None)
    if alerts_cfg is None:
        logger.debug("alerts_route_event_skipped_no_config", extra={"event_code": event_code, "symbol": symbol})
        return None

    try:
        conn = session.connection()
    except Exception:
        bind = session.get_bind()
        conn = bind.connect() if bind is not None else None

    if conn is None:
        logger.warning("alerts_route_event_no_connection", extra={"event_code": event_code, "symbol": symbol})
        return None

    try:
        event_id = router.route_event(
            conn,
            alerts_cfg=alerts_cfg,
            event_code=event_code,
            symbol=symbol,
            mode=mode,
            trading_date=trading_date,
            now_utc=datetime.now(timezone.utc),
            context=context,
            score_at_fire=score_at_fire,
            next_action_code=next_action_code,
        )
        return event_id
    except Exception:
        logger.exception(
            "alerts_route_event_failed",
            extra={"event_code": event_code, "symbol": symbol},
        )
        return None
