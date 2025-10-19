from __future__ import annotations
from typing import Dict, Any
import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from .base import DeliveryResult

def send(event: Dict[str, Any], content: Dict[str, str], chan_cfg: Dict[str, Any]) -> DeliveryResult:
    """
    Generic JSON webhook. Expects chan_cfg: {"url": "...", "headers": {...}}
    """
    if not chan_cfg.get("enabled"):
        return DeliveryResult(status="SKIPPED", response_meta={"reason": "DISABLED"})
    url = chan_cfg.get("url")
    if not url:
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
        with urlopen(req, timeout=10) as resp:
            return DeliveryResult(status="SENT", response_code=getattr(resp, "status", 200))
    except HTTPError as e:
        return DeliveryResult(status="FAILED", response_code=e.code, response_meta={"reason": e.reason})
    except URLError as e:
        return DeliveryResult(status="FAILED", response_meta={"reason": str(e)})
