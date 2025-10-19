from __future__ import annotations
from sqlalchemy import text
from datetime import datetime, timedelta
import logging
from .types import Mode

log = logging.getLogger(__name__)

def exists_event(conn, rule_code: str, symbol: str, trading_date, mode: str, bucket_ord: int) -> bool:
    q = text("""
        SELECT 1 FROM alert_events
         WHERE rule_code=:rule_code AND symbol=:symbol
           AND trading_date=:trading_date AND mode=:mode
           AND bucket_ord=:bucket_ord
         LIMIT 1
    """)
    exists = conn.execute(q, dict(
        rule_code=rule_code, symbol=symbol, trading_date=trading_date, mode=mode, bucket_ord=bucket_ord
    )).first() is not None
    log.debug(
        "exists_event rule=%s symbol=%s trading_date=%s mode=%s bucket=%s => %s",
        rule_code,
        symbol,
        trading_date,
        mode,
        bucket_ord,
        exists,
    )
    return exists

def in_cooldown(conn, rule_code: str, symbol: str, now_utc: datetime) -> bool:
    q = text("""
        SELECT cooldown_until_utc FROM alert_state
         WHERE rule_code=:rule_code AND symbol=:symbol
    """)
    row = conn.execute(q, {"rule_code": rule_code, "symbol": symbol}).first()
    if not row or row[0] is None:
        log.debug("in_cooldown rule=%s symbol=%s => False (no row)", rule_code, symbol)
        return False
    in_cd = now_utc < row[0]
    log.debug(
        "in_cooldown rule=%s symbol=%s now=%s until=%s => %s",
        rule_code,
        symbol,
        now_utc,
        row[0],
        in_cd,
    )
    return in_cd
