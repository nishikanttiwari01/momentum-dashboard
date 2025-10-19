from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.schemas import AlertEvent

router = APIRouter()


def _parse_datetime(value: str) -> Optional[datetime]:
    if not value:
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        fmt_candidates = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S")
        for fmt in fmt_candidates:
            try:
                return datetime.strptime(normalized, fmt)
            except ValueError:
                continue
    return None


def _ensure_aware(value: Optional[Any]) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, str):
        parsed = _parse_datetime(value)
        if parsed is None:
            return None
        value = parsed
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _coerce_literal(value: Optional[str], allowed: Dict[str, str], default: str) -> str:
    if isinstance(value, str):
        key = value.strip().upper()
        if key in allowed:
            return key
    return default


def _normalize_channel_summary(summary: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    if not isinstance(summary, dict):
        return {}
    normalized: Dict[str, Dict[str, Any]] = {}
    for channel, payload in summary.items():
        if isinstance(payload, dict):
            status = _coerce_literal(payload.get("status"), {"SENT": "SENT", "FAILED": "FAILED", "SKIPPED": "SKIPPED"}, "SENT")
            normalized[channel] = {
                "status": status,
                "attempts": payload.get("attempts"),
                "code": payload.get("code"),
                "reason": payload.get("reason"),
            }
        elif isinstance(payload, bool):
            normalized[channel] = {
                "status": "SENT" if payload else "SKIPPED",
                "attempts": 1,
                "code": None,
                "reason": None,
            }
        elif isinstance(payload, str):
            status = _coerce_literal(payload, {"SENT": "SENT", "FAILED": "FAILED", "SKIPPED": "SKIPPED"}, "SENT")
            normalized[channel] = {"status": status, "attempts": 1, "code": None, "reason": None}
        else:
            continue
    return normalized


def _ensure_json_obj(value: Any) -> Optional[Dict[str, Any]]:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    return None


@router.get("/alert-events", response_model=List[AlertEvent])
def list_alert_events(
    symbol: Optional[str] = Query(None, description="Filter by exact symbol."),
    trading_date: Optional[date] = Query(None, description="Filter by trading date (yyyy-mm-dd)."),
    trading_date_from: Optional[date] = Query(None, description="Lower bound for trading date (inclusive)."),
    trading_date_to: Optional[date] = Query(None, description="Upper bound for trading date (inclusive)."),
    severity: Optional[str] = Query(None, description="Filter by severity (INFO|WARN|CRITICAL)."),
    digest_bucket: Optional[str] = Query(None, description="Filter by digest bucket (BUY|SELL|MGMT|SCORE)."),
    mode: Optional[str] = Query(None, description="Filter by mode (EOD|INTRADAY)."),
    rule_code: Optional[str] = Query(None, description="Filter by rule code."),
    next_action_code: Optional[str] = Query(None, description="Filter by next action code."),
    channel_status: Optional[str] = Query(None, description="Require at least one channel with this status."),
    profile: Optional[str] = Query(None, description="Filter by profile identifier."),
    limit: int = Query(200, ge=1, le=500, description="Maximum number of events to return."),
    cursor: Optional[str] = Query(None, description="Opaque cursor; currently interpreted as event id."),
    session: Session = Depends(get_session),
) -> List[AlertEvent]:
    conditions: List[str] = []
    params: Dict[str, Any] = {"limit": limit}

    if symbol:
        conditions.append("e.symbol = :symbol")
        params["symbol"] = symbol.upper()
    if trading_date:
        conditions.append("e.trading_date = :trading_date")
        params["trading_date"] = trading_date
    if trading_date_from:
        conditions.append("e.trading_date >= :trading_date_from")
        params["trading_date_from"] = trading_date_from
    if trading_date_to:
        conditions.append("e.trading_date <= :trading_date_to")
        params["trading_date_to"] = trading_date_to
    if severity:
        conditions.append("e.severity = :severity")
        params["severity"] = severity.upper()
    if digest_bucket:
        conditions.append("e.digest_bucket = :digest_bucket")
        params["digest_bucket"] = digest_bucket.upper()
    if mode:
        conditions.append("e.mode = :mode")
        params["mode"] = mode.upper()
    if rule_code:
        conditions.append("e.rule_code = :rule_code")
        params["rule_code"] = rule_code
    if next_action_code:
        conditions.append("e.next_action_code = :next_action_code")
        params["next_action_code"] = next_action_code
    if profile:
        conditions.append("e.profile = :profile")
        params["profile"] = profile
    if cursor:
        try:
            params["cursor_id"] = int(cursor)
            conditions.append("e.id < :cursor_id")
        except ValueError:
            # Ignore malformed cursor values; treat as no cursor.
            pass

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    stmt = text(
        f"""
        SELECT
            e.id,
            e.symbol,
            e.rule_code,
            e.severity,
            e.digest_bucket,
            e.mode,
            e.trading_date,
            e.bucket_ord,
            e.intraday_bucket_label,
            e.send_type,
            e.digest_id,
            e.title_rendered,
            e.body_rendered,
            e.score_at_fire,
            e.next_action_code,
            e.triggered_by,
            e.profile,
            e.config_version,
            e.context_json,
            e.details_json,
            e.channels_summary_json,
            e.fired_at_utc
        FROM alert_events AS e
        {where_clause}
        ORDER BY e.fired_at_utc DESC, e.id DESC
        LIMIT :limit
        """
    )

    rows = session.execute(stmt, params).mappings().all()
    if not rows:
        return []

    event_ids = [row["id"] for row in rows]
    deliveries_stmt = (
        text(
            """
            SELECT
                d.event_id,
                d.channel,
                d.status,
                d.attempt_no,
                d.sent_at_utc,
                d.response_code,
                d.response_meta
            FROM alert_deliveries AS d
            WHERE d.event_id IN :event_ids
            ORDER BY d.event_id, d.attempt_no
            """
        ).bindparams(bindparam("event_ids", expanding=True))
    )
    delivery_rows = session.execute(deliveries_stmt, {"event_ids": tuple(event_ids)}).mappings().all()

    deliveries_by_event: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for delivery in delivery_rows:
        deliveries_by_event[delivery["event_id"]].append(
            {
                "channel": delivery["channel"],
                "status": delivery["status"],
                "attempt_no": delivery["attempt_no"],
                "sent_at_utc": _ensure_aware(delivery["sent_at_utc"]),
                "response_code": delivery["response_code"],
                "response_meta": _ensure_json_obj(delivery["response_meta"]),
            }
        )

    expected_channel_status = channel_status.upper() if channel_status else None
    events: List[AlertEvent] = []

    for row in rows:
        event_dict: Dict[str, Any] = dict(row)
        event_dict["symbol"] = (event_dict.get("symbol") or "").upper()
        event_dict["severity"] = _coerce_literal(
            event_dict.get("severity"),
            {"INFO": "INFO", "WARN": "WARN", "CRITICAL": "CRITICAL"},
            "INFO",
        )
        event_dict["digest_bucket"] = _coerce_literal(
            event_dict.get("digest_bucket"),
            {"BUY": "BUY", "SELL": "SELL", "MGMT": "MGMT", "SCORE": "SCORE"},
            "SCORE",
        )
        event_dict["context_json"] = _ensure_json_obj(event_dict.get("context_json"))
        event_dict["details_json"] = _ensure_json_obj(event_dict.get("details_json"))
        raw_summary = _ensure_json_obj(event_dict.get("channels_summary_json"))
        event_dict["channels_summary_json"] = _normalize_channel_summary(raw_summary)
        event_dict["fired_at_utc"] = _ensure_aware(event_dict.get("fired_at_utc"))

        deliveries_payload = deliveries_by_event.get(event_dict["id"])
        event_dict["deliveries"] = deliveries_payload if deliveries_payload else None

        candidate = AlertEvent.model_validate(event_dict)

        if expected_channel_status:
            summaries = candidate.channels_summary_json or {}
            if not any(
                (summary.status or "").upper() == expected_channel_status
                for summary in summaries.values()
                if summary
            ):
                continue

        events.append(candidate)

    return events
