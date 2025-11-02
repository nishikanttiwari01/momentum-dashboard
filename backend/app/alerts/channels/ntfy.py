from __future__ import annotations
from typing import Dict, Any
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import logging

from .base import DeliveryResult

log = logging.getLogger(__name__)

def _sanitize_header(value: str, header: str, event_id: Any) -> str:
    try:
        value.encode("latin-1")
        return value
    except UnicodeEncodeError:
        safe = value.encode("latin-1", errors="replace").decode("latin-1")
        log.warning(
            "NTFY header sanitized event_id=%s header=%s original=%r sanitized=%r",
            event_id,
            header,
            value,
            safe,
        )
        return safe


def send(event: Dict[str, Any], content: Dict[str, str], chan_cfg: Dict[str, Any]) -> DeliveryResult:
    """
    Minimal ntfy sender using plain HTTP.
    Expects chan_cfg to supply:
      {"enabled": bool, "server": "...", "topic": "...", "token": "...?"}
    """
    if not chan_cfg.get("enabled", True):
        log.debug("NTFY disabled for event_id=%s", event.get("id"))
        return DeliveryResult(status="SKIPPED", response_meta={"reason": "DISABLED"})

    server = str(chan_cfg.get("server") or "https://ntfy.sh").rstrip("/")
    topic = str(chan_cfg.get("topic") or "").strip()
    if not topic:
        log.debug("NTFY missing topic for event_id=%s", event.get("id"))
        return DeliveryResult(status="SKIPPED", response_meta={"reason": "MISSING_TOPIC"})

    url = f"{server}/{topic}"
    title = content.get("title", "")
    body = content.get("body", "")

    data = body.encode("utf-8")
    req = Request(url, data=data, method="POST")
    req.add_header("Title", _sanitize_header(title, "Title", event.get("id")))
    token = chan_cfg.get("token")
    if token:
        req.add_header("Authorization", f"Bearer {token}")

    try:
        log.debug("NTFY POST event_id=%s url=%s", event.get("id"), url)
        with urlopen(req, timeout=10) as resp:
            code = getattr(resp, "status", 200)
            log.info("NTFY delivered event_id=%s status=%s", event.get("id"), code)
            return DeliveryResult(status="SENT", response_code=code)
    except HTTPError as e:
        log.warning("NTFY HTTP error event_id=%s code=%s reason=%s", event.get("id"), e.code, e.reason)
        return DeliveryResult(status="FAILED", response_code=e.code, response_meta={"reason": e.reason})
    except URLError as e:
        log.warning("NTFY URL error event_id=%s error=%s", event.get("id"), e)
        return DeliveryResult(status="FAILED", response_meta={"reason": str(e)})
