from __future__ import annotations
from typing import Dict, Any, Iterable
import os, smtplib
from email.message import EmailMessage
import logging
from .base import DeliveryResult

log = logging.getLogger(__name__)

def _resolve_smtp(chan_cfg: Dict[str, Any]) -> dict:
    # Prefer YAML chan_cfg, then env vars for personal use
    cfg = {
        "host": chan_cfg.get("host") or os.getenv("SMTP_HOST"),
        "port": int(chan_cfg.get("port") or os.getenv("SMTP_PORT") or 587),
        "user": chan_cfg.get("user") or os.getenv("SMTP_USER"),
        "password": chan_cfg.get("password") or os.getenv("SMTP_PASS"),
        "use_tls": bool(chan_cfg.get("use_tls", True)),
        "from_addr": chan_cfg.get("from") or os.getenv("SMTP_FROM") or "alerts@localhost",
    }
    log.debug("Resolved SMTP config host=%s port=%s user=%s tls=%s", cfg["host"], cfg["port"], cfg["user"], cfg["use_tls"])
    return cfg

def _as_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, (list, tuple, set)):
        return [str(x) for x in v]
    return [str(v)]

def send(event: Dict[str, Any], content: Dict[str, str], chan_cfg: Dict[str, Any]) -> DeliveryResult:
    """
    Simple per-event SMTP sender. Expects chan_cfg.to to be present.
    Reads SMTP_* env if not in YAML.
    """
    if not chan_cfg.get("enabled"):
        log.debug("Email channel disabled for event_id=%s", event.get("id"))
        return DeliveryResult(status="SKIPPED", response_meta={"reason": "DISABLED"})

    to_list = _as_list(chan_cfg.get("to"))
    if not to_list:
        log.warning("Email channel has no recipients for event_id=%s", event.get("id"))
        return DeliveryResult(status="SKIPPED", response_meta={"reason": "NO_RECIPIENTS"})

    smtp_cfg = _resolve_smtp(chan_cfg)
    if not (smtp_cfg["host"] and smtp_cfg["user"] and smtp_cfg["password"]):
        log.error("Email channel missing SMTP configuration for event_id=%s", event.get("id"))
        return DeliveryResult(status="SKIPPED", response_meta={"reason": "SMTP_CONFIG_MISSING"})

    msg = EmailMessage()
    msg["Subject"] = content.get("title", "")
    msg["From"] = smtp_cfg["from_addr"]
    msg["To"] = ", ".join(to_list)
    msg.set_content(content.get("body", ""))

    try:
        log.debug("Connecting to SMTP host=%s port=%s tls=%s", smtp_cfg["host"], smtp_cfg["port"], smtp_cfg["use_tls"])
        with smtplib.SMTP(smtp_cfg["host"], smtp_cfg["port"], timeout=15) as s:
            if smtp_cfg["use_tls"]:
                s.starttls()
            s.login(smtp_cfg["user"], smtp_cfg["password"])
            code, _ = s.sendmail(smtp_cfg["from_addr"], to_list, msg.as_string())
        # smtplib's sendmail returns a dict of failed recipients; empty dict == all good
        if isinstance(code, dict) and code:
            log.error("Email send failed for event_id=%s failed_recipients=%s", event.get("id"), code)
            return DeliveryResult(status="FAILED", response_meta={"failed": code})
        log.info("Email sent for event_id=%s recipients=%s", event.get("id"), to_list)
        return DeliveryResult(status="SENT", response_code=250)
    except smtplib.SMTPResponseException as e:
        log.exception(
            "SMTP response exception for event_id=%s code=%s error=%s",
            event.get("id"),
            e.smtp_code,
            e.smtp_error,
            exc_info=True,
        )
        return DeliveryResult(status="FAILED", response_code=int(e.smtp_code), response_meta={"reason": str(e.smtp_error)})
    except Exception as e:
        log.exception("Email send raised exception for event_id=%s", event.get("id"), exc_info=True)
        return DeliveryResult(status="FAILED", response_meta={"error": repr(e)})
