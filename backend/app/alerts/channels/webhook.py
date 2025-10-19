from __future__ import annotations
from typing import Dict, Any
import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import logging
from .base import DeliveryResult

log = logging.getLogger(__name__)

def send(event: Dict[str, Any], content: Dict[str, str], chan_cfg: Dict[str, Any]) -> DeliveryResult:
    """
    Generic JSON webhook. Expects chan_cfg: {"url": "...", "headers": {...}}
    """
    if not chan_cfg.get("enabled"):
        log.debug("Webhook channel disabled for event_id=%s", event.get("id"))
        return DeliveryResult(status="SKIPPED", response_meta={"reason": "DISABLED"})
    url = chan_cfg.get("url")
    if not url:
        log.warning("Webhook URL missing for event_id=%s", event.get("id"))
        return DeliveryResult(status="SKIPPED", response_meta={"reason": "NO_URL"})

    payload = {
        "event_id": event["id"],
        "code": event["rule_code"],
        "symbol": event["symbol"],
        "severity": event["severity"],
        "digest_bucket": event["digest_bucket"],
        "mode": event["mode"],
        "trading_date": str(event["trading_date"]),
        "bucket_ord": event["bucket_ord"],
        "title": content.get("title", ""),
        "body": content.get("body", ""),
        "score": event.get("score_at_fire"),
        "next_action": event.get("next_action_code"),
        "fired_at_utc": str(event["fired_at_utc"]),
    }
    data = json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in (chan_cfg.get("headers") or {}).items():
        req.add_header(k, v)

    try:
        log.debug("Posting webhook event_id=%s url=%s", event.get("id"), url)
        with urlopen(req, timeout=10) as resp:
            code = getattr(resp, "status", 200)
            log.info("Webhook delivered event_id=%s status=%s", event.get("id"), code)
            return DeliveryResult(status="SENT", response_code=code)
    except HTTPError as e:
        log.warning(
            "Webhook HTTP error event_id=%s code=%s reason=%s",
            event.get("id"),
            e.code,
            e.reason,
        )
        return DeliveryResult(status="FAILED", response_code=e.code, response_meta={"reason": e.reason})
    except URLError as e:
        log.warning("Webhook URL error event_id=%s error=%s", event.get("id"), e)
        return DeliveryResult(status="FAILED", response_meta={"reason": str(e)})
