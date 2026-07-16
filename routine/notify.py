"""Email delivery. Secrets from environment ONLY (see .env.example).

Required env: SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, DIGEST_TO
Optional: SMTP_FROM_NAME (default "Momentum Routine")
"""
from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage
from typing import Optional

log = logging.getLogger(__name__)


class NotifyConfigError(RuntimeError):
    pass


def _cfg() -> dict:
    need = ["SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "DIGEST_TO"]
    missing = [k for k in need if not os.environ.get(k)]
    if missing:
        raise NotifyConfigError(
            f"missing env vars: {missing} — copy .env.example to .env and fill it in"
        )
    return {
        "host": os.environ["SMTP_HOST"],
        "port": int(os.environ.get("SMTP_PORT", "587")),
        "user": os.environ["SMTP_USERNAME"],
        "password": os.environ["SMTP_PASSWORD"],
        "to": [a.strip() for a in os.environ["DIGEST_TO"].split(",") if a.strip()],
        "from_name": os.environ.get("SMTP_FROM_NAME", "Momentum Routine"),
    }


def send_email(subject: str, html: str, text: Optional[str] = None) -> None:
    c = _cfg()
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{c['from_name']} <{c['user']}>"
    msg["To"] = ", ".join(c["to"])
    msg.set_content(text or "This digest requires an HTML-capable mail client.")
    msg.add_alternative(html, subtype="html")
    with smtplib.SMTP(c["host"], c["port"], timeout=30) as s:
        s.ehlo()
        s.starttls()
        s.ehlo()
        s.login(c["user"], c["password"])
        s.send_message(msg)
    log.info("digest sent to %s", c["to"])


def send_error(context: str, exc: BaseException) -> bool:
    """Best-effort failure notification. Returns True if sent."""
    try:
        send_email(
            subject=f"[Momentum ERROR] {context}",
            html=f"<pre>{type(exc).__name__}: {exc}</pre>"
                 "<p>The daily routine FAILED. No signals were produced. "
                 "Check the log in routine/routine_data/out/.</p>",
        )
        return True
    except Exception as e2:  # noqa: BLE001
        log.error("could not send error email either: %s", e2)
        return False
