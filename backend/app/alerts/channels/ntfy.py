from __future__ import annotations
from typing import Dict, Any
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import logging

from .base import DeliveryResult

# New: read global delivery transport if per-alert channel cfg doesn't provide it
try:
    from app.core.config import load as cfg_load
except Exception:
    cfg_load = None  # type: ignore

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


def _global_ntfy_transport() -> dict:
    t: dict[str, Any] = {}
    if cfg_load:
        try:
            alerts = cfg_load().alerts or {}
            t = ((alerts.get("delivery") or {}).get("ntfy") or {})
        except Exception:
            t = {}
    return {
        "server": (t.get("server") or "https://ntfy.sh").rstrip("/"),
        "token": t.get("token"),
        "topic_default": t.get("topic_default") or None,
    }


def _resolve_topic(chan_cfg: Dict[str, Any], topic_default: str | None) -> str | None:
    # Priority: per-alert item.channels.ntfy.topic -> alerts.defaults.channels.ntfy.topic -> delivery.ntfy.topic_default
    if chan_cfg.get("topic"):
        return str(chan_cfg["topic"]).strip() or None

    try:
        if cfg_load:
            defaults_topic = (((cfg_load().alerts or {}).get("defaults") or {}).get("channels") or {}).get("ntfy", {}).get("topic")
            if defaults_topic and str(defaults_topic).strip():
                return str(defaults_topic).strip()
    except Exception:
        pass

    return (str(topic_default).strip() if topic_default else None)


def send(event: Dict[str, Any], content: Dict[str, str], chan_cfg: Dict[str, Any]) -> DeliveryResult:
    """
    Minimal ntfy sender using plain HTTP.
    Transport: alerts.delivery.ntfy (server/token) with per-alert topic overrides.
    """
    if not chan_cfg.get("enabled", True):
        log.debug("NTFY disabled for event_id=%s", event.get("id"))
        return DeliveryResult(status="SKIPPED", response_meta={"reason": "DISABLED"})

    transport = _global_ntfy_transport()
    topic = _resolve_topic(chan_cfg, transport.get("topic_default"))
    if not topic:
        log.debug("NTFY missing topic for event_id=%s", event.get("id"))
        return DeliveryResult(status="SKIPPED", response_meta={"reason": "MISSING_TOPIC"})

    url = f"{transport['server']}/{topic}"
    title = content.get("title", "")
    body = content.get("body", "")

    data = body.encode("utf-8")
    req = Request(url, data=data, method="POST")
    req.add_header("Title", _sanitize_header(title, "Title", event.get("id")))
    if transport.get("token"):
        req.add_header("Authorization", f"Bearer {transport['token']}")

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
