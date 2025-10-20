from __future__ import annotations
from typing import Dict, Any
import os, smtplib, logging
from email.message import EmailMessage

# Keep existing import contract
from .base import DeliveryResult

# New: read global delivery transport if per-alert channel cfg doesn't provide it
try:
    from app.core.config import load as cfg_load
except Exception:  # very defensive: don’t crash sends if config import fails
    cfg_load = None  # type: ignore

log = logging.getLogger(__name__)


def _as_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, (list, tuple, set)):
        return [str(x) for x in v if str(x).strip()]
    return [str(v)]


def _global_email_transport() -> dict:
    """
    Pull SMTP transport from alerts.delivery.email.smtp (v2),
    with ENV fallbacks for personal use.
    """
    smtp: dict[str, Any] = {}
    if cfg_load:
        try:
            alerts = cfg_load().alerts or {}
            smtp = ((alerts.get("delivery") or {}).get("email") or {}).get("smtp") or {}
        except Exception:
            smtp = {}

    # env fallbacks (do not force)
    return {
        "host": smtp.get("host") or os.getenv("SMTP_HOST"),
        "port": int(smtp.get("port") or os.getenv("SMTP_PORT") or 587),
        "username": smtp.get("username") or os.getenv("SMTP_USERNAME") or os.getenv("SMTP_USER"),
        "password": smtp.get("password") or os.getenv("SMTP_PASSWORD") or os.getenv("SMTP_PASS"),
        "use_tls": bool(smtp.get("use_tls", True)),
        "from_addr": smtp.get("from_addr") or os.getenv("SMTP_FROM_ADDR") or smtp.get("username") or os.getenv("SMTP_USERNAME"),
        "from_name": smtp.get("from_name") or os.getenv("SMTP_FROM_NAME") or "Momentum Suite",
        # optional defaults.to (for last-resort recipients)
        "_defaults_to": ((cfg_load().alerts.get("delivery") or {}).get("email") or {}).get("defaults", {}).get("to") if cfg_load else None,  # type: ignore[attr-defined]
    }


def _resolve_recipients(chan_cfg: Dict[str, Any], transport_defaults_to: Any) -> list[str]:
    # Priority: per-alert item.channels.email.to -> alerts.defaults.channels.email.to -> delivery.email.defaults.to
    to_direct = _as_list(chan_cfg.get("to"))
    if to_direct:
        return to_direct

    # try global defaults under alerts.defaults.channels.email.to
    try:
        if cfg_load:
            defaults_to = (((cfg_load().alerts or {}).get("defaults") or {}).get("channels") or {}).get("email", {}).get("to")
            defaults_to_l = _as_list(defaults_to)
            if defaults_to_l:
                return defaults_to_l
    except Exception:
        pass

    # last resort: delivery.email.defaults.to
    return _as_list(transport_defaults_to)


def send(event: Dict[str, Any], content: Dict[str, str], chan_cfg: Dict[str, Any]) -> DeliveryResult:
    """
    SMTP email sender.
    - Recipients resolved from item/defaults/delivery (in that order).
    - Transport resolved from alerts.delivery.email.smtp with ENV fallbacks.
    """
    if not chan_cfg.get("enabled", True):
        log.debug("Email channel disabled for event_id=%s", event.get("id"))
        return DeliveryResult(status="SKIPPED", response_meta={"reason": "DISABLED"})

    transport = _global_email_transport()
    to_list = _resolve_recipients(chan_cfg, transport.get("_defaults_to"))

    if not to_list:
        log.warning("Email channel has no recipients for event_id=%s", event.get("id"))
        return DeliveryResult(status="SKIPPED", response_meta={"reason": "NO_RECIPIENTS"})

    host = transport.get("host")
    user = transport.get("username")
    pwd = transport.get("password")
    port = int(transport.get("port") or 587)
    use_tls = bool(transport.get("use_tls", True))
    from_addr = transport.get("from_addr") or user or "alerts@localhost"
    from_name = transport.get("from_name") or ""

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
