from __future__ import annotations
from sqlalchemy import DateTime, text
from datetime import datetime, timedelta, timezone
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


def get_existing_event(
    conn,
    rule_code: str,
    symbol: str,
    trading_date,
    mode: str,
    bucket_ord: int,
):
    """Return (event_id, score_at_fire) for an existing event in the same
    (rule_code, symbol, trading_date, mode, bucket_ord) slot, else None.

    Used by the "best-in-session" upgrade path: instead of skipping a second
    cross within the same bucket, callers can decide to UPGRADE the row if
    the new signal is materially stronger than the original (e.g. the score
    climbed from 72 to 86 during the same 15-minute bucket).
    """
    q = text("""
        SELECT id, score_at_fire FROM alert_events
         WHERE rule_code=:rule_code AND symbol=:symbol
           AND trading_date=:trading_date AND mode=:mode
           AND bucket_ord=:bucket_ord
         ORDER BY id DESC
         LIMIT 1
    """)
    row = conn.execute(q, dict(
        rule_code=rule_code, symbol=symbol, trading_date=trading_date, mode=mode, bucket_ord=bucket_ord
    )).first()
    if not row:
        return None
    try:
        event_id = int(row[0])
    except Exception:
        return None
    try:
        score = float(row[1]) if row[1] is not None else None
    except Exception:
        score = None
    return event_id, score

def in_cooldown(conn, rule_code: str, symbol: str, now_utc: datetime) -> bool:
    q = text("""
        SELECT cooldown_until_utc FROM alert_state
         WHERE rule_code=:rule_code AND symbol=:symbol
    """).columns(cooldown_until_utc=DateTime(timezone=True))
    row = conn.execute(q, {"rule_code": rule_code, "symbol": symbol}).first()
    if not row or row[0] is None:
        log.debug("in_cooldown rule=%s symbol=%s => False (no row)", rule_code, symbol)
        return False
    cooldown_until = row[0]
    if isinstance(cooldown_until, str):
        try:
            cooldown_until = datetime.fromisoformat(cooldown_until.replace("Z", "+00:00"))
        except ValueError:
            log.warning(
                "Failed to parse cooldown datetime for rule=%s symbol=%s value=%s",
                rule_code,
                symbol,
                cooldown_until,
            )
            return False
    if isinstance(cooldown_until, datetime) and cooldown_until.tzinfo is None:
        cooldown_until = cooldown_until.replace(tzinfo=timezone.utc)
    in_cd = isinstance(cooldown_until, datetime) and now_utc < cooldown_until
    log.debug(
        "in_cooldown rule=%s symbol=%s now=%s until=%s => %s",
        rule_code,
        symbol,
        now_utc,
        cooldown_until,
        in_cd,
    )
    return in_cd
