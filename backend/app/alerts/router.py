from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, Optional, Tuple

from sqlalchemy.engine import Connection

from app.alerts import buckets, dedupe as D, persist as P
from app.alerts.channels.dispatcher import deliver_event
from app.alerts.renderer import render_template
from app.alerts.types import Mode, Severity
from app.core.config import AlertsRoutingConfig, AlertRouteConfig


def _resolve_topic_channels(route: AlertRouteConfig, alerts_cfg: AlertsRoutingConfig) -> list[str]:
    topic_cfg = alerts_cfg.topics.get(route.topic)
    if route.channels is not None:
        return list(route.channels)
    if topic_cfg and topic_cfg.channels:
        return list(topic_cfg.channels)
    return []


def _resolve_cooldown_minutes(route: AlertRouteConfig, alerts_cfg: AlertsRoutingConfig) -> int:
    throttle = route.throttle
    if throttle and throttle.per_symbol_cooldown_min is not None:
        return int(throttle.per_symbol_cooldown_min or 0)
    defaults = alerts_cfg.throttle_defaults
    if defaults and defaults.per_symbol_cooldown_min is not None:
        return int(defaults.per_symbol_cooldown_min or 0)
    return 0


def _resolve_topic_deliveries(
    *,
    route: AlertRouteConfig,
    alerts_cfg: AlertsRoutingConfig,
) -> Dict[str, Dict[str, Any]]:
    delivery = alerts_cfg.delivery
    channels = _resolve_topic_channels(route, alerts_cfg)
    out: Dict[str, Dict[str, Any]] = {}

    if "ntfy" in channels and delivery.ntfy.enabled:
        topic_name: Optional[str]
        if route.topic == "high_signal":
            topic_name = delivery.ntfy.topic_high or delivery.ntfy.topic_low
        elif route.topic == "digest":
            topic_name = delivery.ntfy.topic_low or delivery.ntfy.topic_high
        else:
            topic_name = delivery.ntfy.topic_low or delivery.ntfy.topic_high
        out["ntfy"] = {
            "enabled": True,
            "server": delivery.ntfy.server,
            "topic": topic_name,
        }

    if "email" in channels and delivery.email.enabled:
        smtp_cfg = {
            "host": delivery.email.smtp.host,
            "port": delivery.email.smtp.port,
            "username": delivery.email.smtp.username,
            "password": delivery.email.smtp.password,
            "use_tls": delivery.email.smtp.use_tls,
            "from_addr": delivery.email.smtp.from_addr,
            "from_name": delivery.email.smtp.from_name,
        }
        recipients = list(delivery.email.defaults.to or [])
        out["email"] = {
            "enabled": True,
            "smtp": smtp_cfg,
            "to": recipients,
        }

    # Windows toast: desktop popup + sound. Only emits if a topic actually
    # lists "windows_toast" AND the top-level config has enabled=true. The
    # channel itself further checks an in-process runtime flag so users can
    # silence toasts without restarting the server (see set_runtime_enabled).
    if "windows_toast" in channels and getattr(delivery, "windows_toast", None) is not None:
        toast_cfg = delivery.windows_toast
        if getattr(toast_cfg, "enabled", False):
            out["windows_toast"] = {
                "enabled": True,
                "play_sound": bool(getattr(toast_cfg, "play_sound", True)),
                "sound_alias": getattr(toast_cfg, "sound_alias", "SystemAsterisk"),
                "app_id": getattr(toast_cfg, "app_id", "Momentum Alerts"),
            }

    return out


def _render_ntfy_content(alerts_cfg: AlertsRoutingConfig, event_code: str, context: Dict[str, Any]) -> Dict[str, str]:
    template_map = alerts_cfg.templates.ntfy
    tpl = template_map.get(event_code)
    default_title = f"{event_code} " + "{{symbol}}"
    payload = {"title": tpl or default_title, "body": tpl or context.get("description", "")}
    title, body = render_template(
        payload,
        {"title": default_title, "body": "{{ description }}"},
        context,
    )
    if not body:
        body = title
    return {"title": title, "body": body}


def _render_email_content(alerts_cfg: AlertsRoutingConfig, event_code: str, context: Dict[str, Any]) -> Dict[str, str]:
    template_map = alerts_cfg.templates.email
    tpl = template_map.get(event_code)
    fallback = {
        "title": "[" + event_code + "] {{symbol}}",
        "body": "{{ description }}",
    }
    if tpl:
        payload = {"title": tpl.subject, "body": tpl.body}
    else:
        payload = fallback
    title, body = render_template(payload, fallback, context)
    return {"title": title, "body": body}


def _render_channel_content(
    alerts_cfg: AlertsRoutingConfig,
    event_code: str,
    context: Dict[str, Any],
) -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}
    ntfy_content = _render_ntfy_content(alerts_cfg, event_code, context)
    email_content = _render_email_content(alerts_cfg, event_code, context)
    out["ntfy"] = ntfy_content
    out["email"] = email_content
    return out


def _severity_for_event(route: AlertRouteConfig) -> Severity:
    if route.topic == "high_signal":
        return Severity.CRITICAL
    if route.topic == "digest":
        return Severity.INFO
    return Severity.WARN


def _send_policy(alerts_cfg: AlertsRoutingConfig) -> Dict[str, Any]:
    metadata = alerts_cfg.metadata or {}
    return metadata.get("send_policy") or {}


def _quiet_hours(alerts_cfg: AlertsRoutingConfig) -> Dict[str, Any]:
    metadata = alerts_cfg.metadata or {}
    return metadata.get("quiet_hours") or {}


def route_event(
    conn: Connection,
    *,
    alerts_cfg: AlertsRoutingConfig,
    event_code: str,
    symbol: str,
    mode: Mode,
    trading_date: date,
    now_utc: datetime,
    context: Dict[str, Any],
    score_at_fire: Optional[float] = None,
    next_action_code: Optional[str] = None,
) -> Optional[int]:
    route = alerts_cfg.routes.get(event_code)
    if route is None or not route.enabled:
        return None

    channels_cfg = _resolve_topic_deliveries(route=route, alerts_cfg=alerts_cfg)
    if not channels_cfg:
        return None

    cooldown_min = _resolve_cooldown_minutes(route, alerts_cfg)
    event_cooldown_min = 0
    throttle = route.throttle
    if throttle and throttle.per_event_cooldown_min is not None:
        event_cooldown_min = int(throttle.per_event_cooldown_min or 0)
    elif alerts_cfg.throttle_defaults and alerts_cfg.throttle_defaults.per_event_cooldown_min is not None:
        event_cooldown_min = int(alerts_cfg.throttle_defaults.per_event_cooldown_min or 0)

    EVENT_SCOPE_SYMBOL = "__ALL__"

    if cooldown_min > 0 and D.in_cooldown(conn, event_code, symbol, now_utc):
        return None
    if event_cooldown_min > 0 and D.in_cooldown(conn, event_code, EVENT_SCOPE_SYMBOL, now_utc):
        return None

    bucket_ord = 0
    bucket_label = None
    if mode == Mode.INTRADAY:
        metadata = alerts_cfg.metadata or {}
        tz = metadata.get("timezone", "Asia/Kolkata")
        market_open = metadata.get("market_open_hhmm", "09:15")
        bar_minutes = int(metadata.get("intraday_bar_minutes", 15))
        bucket_ord, bucket_label = buckets.compute_intraday_bucket(now_utc, tz, market_open, bar_minutes)

    # Best-in-session upgrade: instead of hard-skipping any repeat within the
    # same (rule_code, symbol, trading_date, mode, bucket_ord) slot, check
    # whether the new signal is materially stronger. If yes, rewrite the
    # stored row (no re-dispatch, to avoid notification noise). If no, skip.
    existing = D.get_existing_event(conn, event_code, symbol, trading_date, mode.value, bucket_ord)
    if existing is not None:
        existing_id, existing_score = existing
        # Pull upgrade delta from alerts_cfg.metadata (falls back to 5.0 pts).
        # Set to a large number (e.g. 9999) to effectively disable upgrades.
        _meta = alerts_cfg.metadata or {}
        try:
            upgrade_delta = float(_meta.get("upgrade_delta_score", 5.0))
        except (TypeError, ValueError):
            upgrade_delta = 5.0

        should_upgrade = (
            score_at_fire is not None
            and existing_score is not None
            and float(score_at_fire) >= float(existing_score) + upgrade_delta
        )
        if not should_upgrade:
            return None

        # Upgrade path: re-render templates against the fresh context, rewrite
        # the stored row in place, and return the existing id. We deliberately
        # do NOT re-dispatch channels — the first notification is sufficient;
        # the upgrade is for record-keeping (analytics / UI / replay) only.
        upgraded_content = _render_channel_content(alerts_cfg, event_code, context)
        P.update_event_on_upgrade(
            conn,
            event_id=existing_id,
            title_rendered=upgraded_content["email"]["title"],
            body_rendered=upgraded_content["email"]["body"],
            score_at_fire=score_at_fire,
            next_action_code=next_action_code,
            context_json=context,
            fired_at_utc=now_utc,
        )
        return existing_id

    rendered_content = _render_channel_content(alerts_cfg, event_code, context)
    base_content = (
        rendered_content.get("email")
        or rendered_content.get("ntfy")
        or {"title": event_code, "body": context.get("description", "")}
    )
    severity = _severity_for_event(route)
    digest_bucket = route.topic or "general"

    event_id = P.insert_event(
        conn,
        rule_code=event_code,
        symbol=symbol,
        severity=severity.value,
        digest_bucket=digest_bucket,
        mode=mode.value,
        trading_date=trading_date,
        bucket_ord=bucket_ord,
        intraday_bucket_label=bucket_label,
        send_type="REALTIME",
        title_rendered=rendered_content["email"]["title"],
        body_rendered=rendered_content["email"]["body"],
        score_at_fire=score_at_fire,
        next_action_code=next_action_code,
        triggered_by="SCHEDULE",
        profile=context.get("profile"),
        config_version=alerts_cfg.version if isinstance(alerts_cfg.version, int) else None,
        context_json=context,
        details_json={},
        channels_summary_json={},
        fired_at_utc=now_utc,
    )

    summary = deliver_event(
        conn,
        event={"id": event_id, "rule_code": event_code, "symbol": symbol, "severity": severity.value},
        content=base_content,
        channel_contents=rendered_content,
        channels_cfg=channels_cfg,
        send_policy=_send_policy(alerts_cfg),
        quiet_hours=_quiet_hours(alerts_cfg),
        local_tz=alerts_cfg.metadata.get("timezone", "Asia/Kolkata") if alerts_cfg.metadata else "Asia/Kolkata",
        severity=severity.value,
    )

    cooldown_until = None
    event_cooldown_until = None
    if cooldown_min > 0:
        cooldown_until = now_utc + timedelta(minutes=cooldown_min)
    if event_cooldown_min > 0:
        event_cooldown_until = now_utc + timedelta(minutes=event_cooldown_min)
    P.upsert_state(
        conn,
        rule_code=event_code,
        symbol=symbol,
        fired_at_utc=now_utc,
        trading_date=trading_date,
        mode=mode.value,
        bucket_ord=bucket_ord,
        score_at_fire=score_at_fire,
        next_action_code=next_action_code,
        cooldown_until_utc=cooldown_until,
    )
    if event_cooldown_until is not None:
        P.upsert_state(
            conn,
            rule_code=event_code,
            symbol=EVENT_SCOPE_SYMBOL,
            fired_at_utc=now_utc,
            trading_date=trading_date,
            mode=mode.value,
            bucket_ord=bucket_ord,
            score_at_fire=score_at_fire,
            next_action_code=next_action_code,
            cooldown_until_utc=event_cooldown_until,
        )
    return event_id
