from __future__ import annotations
from typing import Dict, Any
import smtplib, logging
from email.message import EmailMessage

# Keep existing import contract
from .base import DeliveryResult

log = logging.getLogger(__name__)


def _as_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, (list, tuple, set)):
        return [str(x) for x in v if str(x).strip()]
    return [str(v)]


def send(event: Dict[str, Any], content: Dict[str, str], chan_cfg: Dict[str, Any]) -> DeliveryResult:
    """
    SMTP email sender.
    Expects chan_cfg to supply:
      {
        "enabled": bool,
        "smtp": {"host": ..., "port": ..., "username": ..., "password": ..., "use_tls": bool, "from_addr": ..., "from_name": ...},
        "to": ["recipient@example.com", ...]
      }
    """
    if not chan_cfg.get("enabled", True):
        log.debug("Email channel disabled for event_id=%s", event.get("id"))
        return DeliveryResult(status="SKIPPED", response_meta={"reason": "DISABLED"})

    smtp_cfg = chan_cfg.get("smtp") or {}
    to_list = _as_list(chan_cfg.get("to"))

    if not to_list:
        log.warning("Email channel has no recipients for event_id=%s", event.get("id"))
        return DeliveryResult(status="SKIPPED", response_meta={"reason": "NO_RECIPIENTS"})

    host = smtp_cfg.get("host")
    user = smtp_cfg.get("username")
    pwd = smtp_cfg.get("password")
    port = int(smtp_cfg.get("port") or 587)
    use_tls = bool(smtp_cfg.get("use_tls", True))
    from_addr = smtp_cfg.get("from_addr") or user or "alerts@localhost"
    from_name = smtp_cfg.get("from_name") or ""

    if not (host and user and pwd):
        log.error("Email channel missing SMTP transport config (host/user/password) for event_id=%s", event.get("id"))
        return DeliveryResult(status="SKIPPED", response_meta={"reason": "SMTP_CONFIG_MISSING"})

    msg = EmailMessage()
    msg["Subject"] = content.get("title", "")
    msg["From"] = f"{from_name} <{from_addr}>" if from_name else from_addr
    msg["To"] = ", ".join(to_list)
    msg.set_content(content.get("body", ""))

    try:
        log.debug("SMTP connect host=%s port=%s tls=%s user=%s", host, port, use_tls, user)
        with smtplib.SMTP(host, port, timeout=20) as s:
            s.ehlo()
            if use_tls:
                s.starttls()
                s.ehlo()
            s.login(user, pwd)
            # smtplib returns {} for success; dict of failures otherwise
            failed = s.sendmail(from_addr, to_list, msg.as_string())
        if isinstance(failed, dict) and failed:
            log.error("Email send had failed recipients for event_id=%s failed=%s", event.get("id"), failed)
            return DeliveryResult(status="FAILED", response_meta={"failed": failed})
        log.info("Email sent event_id=%s to=%s", event.get("id"), to_list)
        return DeliveryResult(status="SENT", response_code=250)
    except smtplib.SMTPResponseException as e:
        log.exception("SMTP response error event_id=%s code=%s err=%s", event.get("id"), e.smtp_code, e.smtp_error)
        return DeliveryResult(status="FAILED", response_code=int(e.smtp_code), response_meta={"reason": str(e.smtp_error)})
    except Exception as e:
        log.exception("Email send exception event_id=%s", event.get("id"))
        return DeliveryResult(status="FAILED", response_meta={"error": repr(e)})
