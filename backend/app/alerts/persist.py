from __future__ import annotations
from typing import Dict, Any, Optional
from sqlalchemy import text
from datetime import datetime, date
import json
import logging

log = logging.getLogger(__name__)

def insert_event(conn, *,
                 rule_code: str,
                 symbol: str,
                 severity: str,
                 digest_bucket: str,
                 mode: str,
                 trading_date: date,
                 bucket_ord: int,
                 intraday_bucket_label: Optional[str],
                 send_type: str,
                 title_rendered: str,
                 body_rendered: str,
                 score_at_fire: Optional[float],
                 next_action_code: Optional[str],
                 triggered_by: str,
                 profile: Optional[str],
                 config_version: Optional[int],
                 context_json: Dict[str, Any],
                 details_json: Dict[str, Any],
                 channels_summary_json: Dict[str, Any],
                 fired_at_utc: datetime) -> int:
    log.debug(
        "Inserting alert_event rule=%s symbol=%s severity=%s mode=%s trading_date=%s bucket=%s",
        rule_code,
        symbol,
        severity,
        mode,
        trading_date,
        bucket_ord,
    )
    q = text("""
        INSERT INTO alert_events
        (rule_code, symbol, severity, digest_bucket, mode, trading_date,
         bucket_ord, intraday_bucket_label, send_type,
         title_rendered, body_rendered, score_at_fire, next_action_code,
         triggered_by, profile, config_version,
         context_json, details_json, channels_summary_json, fired_at_utc)
        VALUES
        (:rule_code,:symbol,:severity,:digest_bucket,:mode,:trading_date,
         :bucket_ord,:intraday_bucket_label,:send_type,
         :title_rendered,:body_rendered,:score_at_fire,:next_action_code,
         :triggered_by,:profile,:config_version,
         :context_json,:details_json,:channels_summary_json,:fired_at_utc)
    """)
    conn.execute(q, {
        "rule_code": rule_code,
        "symbol": symbol,
        "severity": severity,
        "digest_bucket": digest_bucket,
        "mode": mode,
        "trading_date": trading_date,
        "bucket_ord": bucket_ord,
        "intraday_bucket_label": intraday_bucket_label,
        "send_type": send_type,
        "title_rendered": title_rendered,
        "body_rendered": body_rendered,
        "score_at_fire": score_at_fire,
        "next_action_code": next_action_code,
        "triggered_by": triggered_by,
        "profile": profile,
        "config_version": config_version,
        "context_json": json.dumps(context_json or {}),
        "details_json": json.dumps(details_json or {}),
        "channels_summary_json": json.dumps(channels_summary_json or {}),
        "fired_at_utc": fired_at_utc,
    })
    row = conn.execute(text("SELECT last_insert_rowid()")).first()
    event_id = int(row[0]) if row else 0
    log.debug("Inserted alert_event id=%s rule=%s symbol=%s", event_id, rule_code, symbol)
    return event_id

def insert_delivery(conn, *, event_id: int, channel: str, status: str,
                    attempt_no: int = 1, sent_at_utc: datetime | None = None,
                    response_code: int | None = None, response_meta: dict | None = None) -> None:
    log.debug(
        "Recording delivery event_id=%s channel=%s status=%s attempt=%s code=%s",
        event_id,
        channel,
        status,
        attempt_no,
        response_code,
    )
    q = text("""
        INSERT INTO alert_deliveries
        (event_id, channel, status, attempt_no, sent_at_utc, response_code, response_meta)
        VALUES (:event_id, :channel, :status, :attempt_no, :sent_at_utc, :response_code, :response_meta)
    """)
    conn.execute(q, {
        "event_id": event_id,
        "channel": channel,
        "status": status,
        "attempt_no": attempt_no,
        "sent_at_utc": sent_at_utc,
        "response_code": response_code,
        "response_meta": json.dumps(response_meta or {}),
    })

def delivery_exists(conn, *, event_id: int, channel: str) -> bool:
    row = conn.execute(text("""
        SELECT 1 FROM alert_deliveries
         WHERE event_id=:event_id AND channel=:channel AND status='SENT'
         LIMIT 1
    """), {"event_id": event_id, "channel": channel}).first()
    exists = row is not None
    log.debug("Delivery exists check event_id=%s channel=%s => %s", event_id, channel, exists)
    return exists

def update_event_channels_summary(conn, *, event_id: int, summary: dict) -> None:
    log.debug("Updating channels summary event_id=%s summary_keys=%s", event_id, list(summary.keys()))
    conn.execute(text("""
        UPDATE alert_events
           SET channels_summary_json = :summary
         WHERE id = :event_id
    """), {"summary": json.dumps(summary or {}), "event_id": event_id})

def upsert_state(conn, *, rule_code: str, symbol: str,
                 fired_at_utc, trading_date, mode: str, bucket_ord: int,
                 score_at_fire: float | None, next_action_code: str | None,
                 cooldown_until_utc) -> None:
    log.debug(
        "Upserting alert state rule=%s symbol=%s mode=%s bucket=%s cooldown=%s",
        rule_code,
        symbol,
        mode,
        bucket_ord,
        cooldown_until_utc,
    )
    upd = text("""
        UPDATE alert_state
           SET last_fired_at_utc=:fired_at_utc,
               last_trading_date=:trading_date,
               last_mode=:mode,
               last_bucket_ord=:bucket_ord,
               last_score_at_fire=:score_at_fire,
               last_next_action_code=:next_action_code,
               cooldown_until_utc=:cooldown_until_utc
         WHERE rule_code=:rule_code AND symbol=:symbol
    """)
    res = conn.execute(upd, {
        "fired_at_utc": fired_at_utc,
        "trading_date": trading_date,
        "mode": mode,
        "bucket_ord": bucket_ord,
        "score_at_fire": score_at_fire,
        "next_action_code": next_action_code,
        "cooldown_until_utc": cooldown_until_utc,
        "rule_code": rule_code,
        "symbol": symbol,
    })
    if res.rowcount == 0:
        log.debug("No existing state found for rule=%s symbol=%s; inserting new row", rule_code, symbol)
        ins = text("""
            INSERT INTO alert_state
            (rule_code, symbol, last_fired_at_utc, last_trading_date, last_mode, last_bucket_ord,
             last_score_at_fire, last_next_action_code, cooldown_until_utc)
            VALUES
            (:rule_code, :symbol, :fired_at_utc, :trading_date, :mode, :bucket_ord,
             :score_at_fire, :next_action_code, :cooldown_until_utc)
        """)
        conn.execute(ins, {
            "rule_code": rule_code,
            "symbol": symbol,
            "fired_at_utc": fired_at_utc,
            "trading_date": trading_date,
            "mode": mode,
            "bucket_ord": bucket_ord,
            "score_at_fire": score_at_fire,
            "next_action_code": next_action_code,
            "cooldown_until_utc": cooldown_until_utc,
        })
