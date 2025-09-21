# backend/app/notifs/ntfy.py
from __future__ import annotations
import os
import logging
import requests

log = logging.getLogger(__name__)

def _env(name: str, default: str = "") -> str:
    v = os.getenv(name)
    return v if v is not None else default

def notify(title: str, body: str, tags: str | None = None, priority: str = "high") -> bool:
    """
    Send an ntfy push. Returns True on successful POST, False otherwise.
    Logs clearly if NTFY_TOPIC is missing or if the POST fails.
    """
    server = _env("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    topic  = _env("NTFY_TOPIC", "momentum-alerts-nishi")
    token  = _env("NTFY_TOKEN", "")

    if not topic:
        # Loud and clear: topic missing in this uvicorn process
        log.warning("ntfy disabled: NTFY_TOPIC not set; skipping send", extra={"title": title})
        return False

    url = f"{server}/{topic}"
    headers = {"Title": title, "Priority": priority}
    if tags:
        headers["Tags"] = tags

    # sanitize token; only send header when truly non-empty
    token = (token or "").strip().strip('"').strip("'")
    if token.lower() in {"none", "null", "false", "0"}:
        token = ""

    if token:
        headers["Authorization"] = f"Bearer {token}"


    # preflight log
    log.info("ntfy attempt", extra={"topic": topic, "url": url, "title": title, "tags": tags})

    try:
        r = requests.post(url, data=body.encode("utf-8"), headers=headers, timeout=8)
        r.raise_for_status()
        data = r.json()
        log.info("ntfy sent", extra={"topic": topic, "id": data.get("id"), "priority": data.get("priority")})
        return True
    except Exception as e:
        log.exception("ntfy send failed", extra={"topic": topic, "error": str(e)})
        return False
