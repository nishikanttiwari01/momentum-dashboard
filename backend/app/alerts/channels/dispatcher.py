from __future__ import annotations
from typing import Dict, Any
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo
import logging
from .base import DeliveryResult
from .. import persist as P

log = logging.getLogger(__name__)

# simple in-process rate counters keyed by channel -> (window_minute, count)
_RATE_BUCKET: dict[str, tuple[int, int]] = {}

def _in_quiet_hours(now_local: datetime, quiet_hours: dict[str, Any], severity: str) -> bool:
    if not quiet_hours or not quiet_hours.get("enabled"):
        return False
    overrides = set(quiet_hours.get("override_for_severity") or [])
    if severity in overrides:
        return False
    try:
        hh_from, mm_from = [int(x) for x in str(quiet_hours["local_from"]).split(":")]
        hh_to, mm_to = [int(x) for x in str(quiet_hours["local_to"]).split(":")]
        t = now_local.time()
        a, b = time(hh_from, mm_from), time(hh_to, mm_to)
        if a <= b:
            in_window = a <= t < b
        else:
            # spans midnight
            in_window = not (b <= t < a)
        log.debug("Quiet hours check time=%s window=%s-%s severity=%s => %s", t, a, b, severity, in_window)
        return in_window
    except Exception as exc:
        log.warning("Quiet hours parsing failed data=%s error=%s", quiet_hours, exc)
        return False

def _rate_ok(channel: str, limit_per_minute: int) -> bool:
    if limit_per_minute <= 0:
        return True
    now_min = int(datetime.now(timezone.utc).timestamp() // 60)
    prev = _RATE_BUCKET.get(channel)
    if not prev or prev[0] != now_min:
        _RATE_BUCKET[channel] = (now_min, 1)
        log.debug("Rate bucket reset channel=%s minute=%s", channel, now_min)
        return True
    if prev[1] < limit_per_minute:
        _RATE_BUCKET[channel] = (prev[0], prev[1] + 1)
        log.debug(
            "Rate bucket increment channel=%s minute=%s count=%s limit=%s",
            channel,
            prev[0],
            prev[1] + 1,
            limit_per_minute,
        )
        return True
    log.info("Channel %s exceeded rate limit %s/min for window=%s", channel, limit_per_minute, prev[0])
    return False

def _merge_channel_cfg(defaults: dict, override: dict | None) -> dict:
    out = dict(defaults or {})
    if override:
        for k, v in override.items():
            out[k] = v
    log.debug("Merged channel cfg defaults_keys=%s override_keys=%s", list((defaults or {}).keys()), list((override or {}).keys()))
    return out

def deliver_event(
    conn,
    *,
    event: Dict[str, Any],
    content: Dict[str, str],            # {"title": ..., "body": ...}
    channel_contents: Dict[str, Dict[str, str]] | None,
    channels_cfg: Dict[str, Any],       # effective config: {"ntfy":{...}, "email":{...}, "webhook":{...}}
    send_policy: Dict[str, Any] | None,
    quiet_hours: Dict[str, Any] | None,
    local_tz: str,
    severity: str,
) -> Dict[str, Any]:
    """
    Sends the event via all enabled channels. Persists one row per attempt in alert_deliveries,
    and returns a compact summary object to save into alert_events.channels_summary_json.
    """
    summary: Dict[str, Any] = {}
    now_local = datetime.now(ZoneInfo(local_tz))
    log.info(
        "Delivering alert event id=%s rule=%s severity=%s channels=%s",
        event["id"],
        event["rule_code"],
        severity,
        list((channels_cfg or {}).keys()),
    )

    # Quiet hours check (per event, before any channel)
    is_quiet = _in_quiet_hours(now_local, quiet_hours or {}, severity)
    if is_quiet:
        log.info("Quiet hours active for severity=%s event_id=%s", severity, event["id"])

    retry_cfg = ((send_policy or {}).get("retry")) or {}
    attempts = int(retry_cfg.get("attempts", 1))
    backoff = list(retry_cfg.get("backoff_seconds", [])) or []

    rate_cfg = ((send_policy or {}).get("rate_limit")) or {}
    ntfy_rate = int(rate_cfg.get("ntfy_per_minute", 0))
    email_rate = int(rate_cfg.get("email_per_minute", 0))
    webhook_rate = int(rate_cfg.get("webhook_per_minute", 0))

    # Helpers to run a channel with attempts / rate / quiet handling
    def run_channel(name: str, sender_func, limit_per_min: int, chan_cfg: dict[str, Any]):
        nonlocal summary
        if not chan_cfg or not chan_cfg.get("enabled", False):
            log.debug("Channel %s disabled via config", name)
            return
        # idempotency: skip if already SENT for this (event, channel)
        if P.delivery_exists(conn, event_id=event["id"], channel=name):
            summary[name] = {"status": "SKIPPED", "reason": "DUPLICATE"}
            log.debug("Channel %s already delivered for event_id=%s", name, event["id"])
            return

        if is_quiet:
            P.insert_delivery(conn, event_id=event["id"], channel=name, status="SKIPPED",
                              attempt_no=1, response_code=None,
                              response_meta={"reason": "QUIET_HOURS"})
            summary[name] = {"status": "SKIPPED", "reason": "QUIET_HOURS"}
            log.debug("Channel %s skipped due to quiet hours event_id=%s", name, event["id"])
            return

        if not _rate_ok(name, limit_per_min):
            P.insert_delivery(conn, event_id=event["id"], channel=name, status="SKIPPED",
                              attempt_no=1, response_code=None,
                              response_meta={"reason": "RATELIMIT"})
            summary[name] = {"status": "SKIPPED", "reason": "RATELIMIT"}
            log.warning("Channel %s rate limited; event_id=%s", name, event["id"])
            return

        last_result: DeliveryResult | None = None
        channel_content = (channel_contents or {}).get(name, content)
        for i in range(1, max(1, attempts) + 1):
            try:
                log.debug("Channel %s attempt=%s sending event_id=%s", name, i, event["id"])
                last_result = sender_func(event, channel_content, chan_cfg)
            except Exception as e:
                log.exception("Channel %s attempt=%s failed event_id=%s", name, i, event["id"], exc_info=True)
                last_result = DeliveryResult(status="FAILED", response_code=None, response_meta={"error": repr(e)}, attempts=i)

            # persist attempt
            P.insert_delivery(conn,
                              event_id=event["id"],
                              channel=name,
                              status=last_result.status,
                              attempt_no=i,
                              response_code=last_result.response_code,
                              response_meta=last_result.response_meta)

            if last_result.status == "SENT":
                log.info("Channel %s sent event_id=%s code=%s", name, event["id"], last_result.response_code)
                break
            # backoff if another attempt remains
            if i < attempts and backoff:
                from time import sleep
                wait = backoff[min(i-1, len(backoff)-1)]
                log.debug("Channel %s backing off %s seconds before attempt %s", name, wait, i + 1)
                sleep(wait)

        summary[name] = {
            "status": last_result.status if last_result else "FAILED",
            "attempts": (last_result.attempts if last_result else 1),
            "code": (last_result.response_code if last_result else None),
        }

    # Load channel senders
    from .ntfy import send as send_ntfy
    from .email import send as send_email
    from .webhook import send as send_webhook

    # Dispatch
    cfg_ntfy = (channels_cfg or {}).get("ntfy") or {}
    cfg_email = (channels_cfg or {}).get("email") or {}
    cfg_hook = (channels_cfg or {}).get("webhook") or {}

    run_channel("ntfy", send_ntfy, ntfy_rate, cfg_ntfy)
    run_channel("email", send_email, email_rate, cfg_email)
    run_channel("webhook", send_webhook, webhook_rate, cfg_hook)

    # Save summary back to the event row
    P.update_event_channels_summary(conn, event_id=event["id"], summary=summary)
    log.info("Delivery summary event_id=%s summary=%s", event["id"], summary)
    return summary
