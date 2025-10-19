from __future__ import annotations
from sqlalchemy import text
from datetime import datetime, timedelta
from .types import Mode

def exists_event(conn, rule_code: str, symbol: str, trading_date, mode: str, bucket_ord: int) -> bool:
    q = text("""
        SELECT 1 FROM alert_events
         WHERE rule_code=:rule_code AND symbol=:symbol
           AND trading_date=:trading_date AND mode=:mode
           AND bucket_ord=:bucket_ord
         LIMIT 1
    """)
    return conn.execute(q, dict(
        rule_code=rule_code, symbol=symbol, trading_date=trading_date, mode=mode, bucket_ord=bucket_ord
    )).first() is not None

def in_cooldown(conn, rule_code: str, symbol: str, now_utc: datetime) -> bool:
    q = text("""
        SELECT cooldown_until_utc FROM alert_state
         WHERE rule_code=:rule_code AND symbol=:symbol
    """)
    row = conn.execute(q, {"rule_code": rule_code, "symbol": symbol}).first()
    if not row or row[0] is None:
        return False
    return now_utc < row[0]
