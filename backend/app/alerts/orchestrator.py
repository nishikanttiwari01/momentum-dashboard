from __future__ import annotations
from typing import Iterable, Dict, Any
from datetime import datetime, date
from sqlalchemy.engine import Connection
from .types import Mode
from .base import EvalContext
from . import buckets
from . import filters as F
from . import persist as P
from . import dedupe as D
from .registry import load_rule_handler
from .channels.dispatcher import deliver_event

def _resolve_defaults(alerts_cfg: Dict[str, Any]) -> Dict[str, Any]:
    return alerts_cfg.get("defaults", {}) if alerts_cfg else {}

def _resolve_thresholds(alerts_cfg: Dict[str, Any]) -> Dict[str, Any]:
    return alerts_cfg.get("thresholds", {}) if alerts_cfg else {}

def _resolve_templates(alerts_cfg: Dict[str, Any]) -> Dict[str, Any]:
    return (alerts_cfg.get("templates") or {}).get("default", {"title":"{{ code }} • {{ symbol }}","body":"{{ description }}"})

def _resolve_metadata(alerts_cfg: Dict[str, Any]) -> Dict[str, Any]:
    return alerts_cfg.get("metadata", {}) if alerts_cfg else {}

def run(
    conn: Connection,
    *,
    alerts_cfg: Dict[str, Any],
    symbols: Iterable[str],
    mode: Mode,
    trading_date: date,
    now_utc: datetime,
    metric_getter,
    run_ctx: Dict[str, Any] | None = None,
) -> list[int]:
    run_ctx = run_ctx or {}
    defaults = _resolve_defaults(alerts_cfg)
    thresholds = _resolve_thresholds(alerts_cfg)
    items = list(alerts_cfg.get("items") or [])
    templates_default = _resolve_templates(alerts_cfg)
    metadata = _resolve_metadata(alerts_cfg)

    profile = (alerts_cfg.get("profiles") or {}).get("active")
    config_version = alerts_cfg.get("version")
    tz = metadata.get("timezone", "Asia/Kolkata")
    intraday_bar = int(metadata.get("intraday_bar_minutes", 15))
    market_open = metadata.get("market_open_hhmm", "09:15")
    bucket_ord, bucket_label = (0, None)
    if mode == Mode.INTRADAY:
        bucket_ord, bucket_label = buckets.compute_intraday_bucket(now_utc, tz, market_open, intraday_bar)

    max_alerts_per_run = int((defaults.get("throttles") or {}).get("max_alerts_per_run", 999999))
    max_per_symbol_day = int((defaults.get("throttles") or {}).get("max_alerts_per_symbol_day", 999999))

    created_ids: list[int] = []
    per_symbol_count: dict[str, int] = {}

    for item in items:
        mode_cfg = item.get("mode") or {}
        if mode == Mode.INTRADAY and not mode_cfg.get("allow_intraday", False):
            continue
        if mode == Mode.EOD and not mode_cfg.get("allow_eod", True):
            continue

        rule_code = str(item["code"]).strip()
        digest_bucket = item.get("digest_bucket") or "SCORE"
        severity = str(item.get("severity") or defaults.get("severity") or "INFO")
        item_filters = item.get("filters") or {}
        template_cfg = item.get("template") or None
        send_type = "IMMEDIATE"
        channels_cfg_eff = (defaults.get("channels") or {}).copy()
        chan_override = item.get("channels") or {}
        channels_cfg_eff.update(chan_override)

        handler = load_rule_handler(rule_code)

        for sym in symbols:
            if len(created_ids) >= max_alerts_per_run:
                break
            if per_symbol_count.get(sym, 0) >= max_per_symbol_day:
                continue

            ctx = EvalContext(
                mode=mode,
                trading_date=trading_date,
                now_utc=now_utc,
                profile=profile,
                config_version=config_version,
                defaults=defaults,
                thresholds=thresholds,
                item_cfg=item,
                metric_getter=metric_getter,
                triggered_by=str(run_ctx.get("triggered_by") or "SCHEDULE"),
            )

            ok, capture = F.passes_filters(ctx, sym, item_filters)
            if not ok:
                continue

            if D.exists_event(conn, rule_code, sym, trading_date, mode.value, bucket_ord):
                continue
            if D.in_cooldown(conn, rule_code, sym, now_utc):
                continue

            res = handler.evaluate(ctx, sym)
            if res is None or res.triggered is not True:
                from .base import EvalResult
                res = EvalResult(triggered=True, severity=severity, context_json={}, details_json={})

            context_json = {
                "code": rule_code,
                "symbol": sym,
                "description": item.get("description") or "",
                "mode": mode.value,
                "score": capture.get("score"),
                **capture,
                **(res.context_json or {}),
            }
            details_json = res.details_json or {}

            from .renderer import render_template
            title, body = render_template(template_cfg, templates_default, context_json)

            event_id = P.insert_event(
                conn,
                rule_code=rule_code,
                symbol=sym,
                severity=str(res.severity),
                digest_bucket=digest_bucket,
                mode=mode.value,
                trading_date=trading_date,
                bucket_ord=bucket_ord,
                intraday_bucket_label=bucket_label,
                send_type=send_type,
                title_rendered=title,
                body_rendered=body,
                score_at_fire=context_json.get("score"),
                next_action_code=context_json.get("next_action_code"),
                triggered_by=ctx.triggered_by,
                profile=ctx.profile,
                config_version=ctx.config_version,
                context_json=context_json,
                details_json=details_json,
                channels_summary_json={},  # will be updated after dispatch
                fired_at_utc=now_utc,
            )
            created_ids.append(event_id)
            per_symbol_count[sym] = per_symbol_count.get(sym, 0) + 1

            # Channel delivery (ntfy/email/webhook)
            event_row = {
                "id": event_id,
                "rule_code": rule_code,
                "symbol": sym,
                "severity": str(res.severity),
                "digest_bucket": digest_bucket,
                "mode": mode.value,
                "trading_date": trading_date,
                "bucket_ord": bucket_ord,
                "fired_at_utc": now_utc,
                "score_at_fire": context_json.get("score"),
                "next_action_code": context_json.get("next_action_code"),
            }
            deliver_event(
                conn,
                event=event_row,
                content={"title": title, "body": body},
                channels_cfg=channels_cfg_eff,
                send_policy=defaults.get("send_policy"),
                quiet_hours=defaults.get("quiet_hours"),
                local_tz=tz,
                severity=str(res.severity),
            )

            cooldown_min = int((item.get("repeat_policy") or {}).get("min_cooldown_minutes", (defaults.get("repeat_policy") or {}).get("min_cooldown_minutes", 0)))
            cooldown_until = None
            if cooldown_min > 0:
                from datetime import timedelta
                cooldown_until = now_utc + timedelta(minutes=cooldown_min)
            P.upsert_state(
                conn,
                rule_code=rule_code,
                symbol=sym,
                fired_at_utc=now_utc,
                trading_date=trading_date,
                mode=mode.value,
                bucket_ord=bucket_ord,
                score_at_fire=context_json.get("score"),
                next_action_code=context_json.get("next_action_code"),
                cooldown_until_utc=cooldown_until,
            )

    return created_ids
