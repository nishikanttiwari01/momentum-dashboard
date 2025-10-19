from __future__ import annotations
from typing import Dict, Any
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from .base import DeliveryResult

def send(event: Dict[str, Any], content: Dict[str, str], chan_cfg: Dict[str, Any]) -> DeliveryResult:
    """
    Minimal ntfy sender using plain HTTP.
    Expects chan_cfg: {"topic": "...", "server": "https://ntfy.sh", "token": "..."}.
    """
    topic = chan_cfg.get("topic")
    if not (chan_cfg.get("enabled") and topic):
        return DeliveryResult(status="SKIPPED", response_meta={"reason": "DISABLED_OR_MISSING_TOPIC"})

    server = (chan_cfg.get("server") or "https://ntfy.sh").rstrip("/")
    url = f"{server}/{topic}"
    title = content.get("title", "")
    body = content.get("body", "")

    data = body.encode("utf-8")
    req = Request(url, data=data, method="POST")
    req.add_header("Title", title)
    if chan_cfg.get("token"):
        req.add_header("Authorization", f"Bearer {chan_cfg['token']}")

    try:
        with urlopen(req, timeout=10) as resp:
            return DeliveryResult(status="SENT", response_code=getattr(resp, "status", 200))
    except HTTPError as e:
        return DeliveryResult(status="FAILED", response_code=e.code, response_meta={"reason": e.reason})
    except URLError as e:
        return DeliveryResult(status="FAILED", response_meta={"reason": str(e)})
