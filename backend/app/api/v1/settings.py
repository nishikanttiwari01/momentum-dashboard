#backend/app/api/v1/settings.py
import asyncio
import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, Literal, Optional
from zoneinfo import ZoneInfo

import anyio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.alerts.channels.email import send as send_email_channel
from app.alerts.channels.ntfy import send as send_ntfy_channel
from app.alerts.channels.windows_toast import (
    get_runtime_enabled as toast_get_runtime_enabled,
    send as send_windows_toast_channel,
    set_runtime_enabled as toast_set_runtime_enabled,
)
from app.cli.backfill import main as backfill_main
from app.core import config as config_module
from ._examples import load_example

router = APIRouter()
log = logging.getLogger(__name__)


class WindowsToastToggle(BaseModel):
    enabled: Optional[bool] = None


class TestAlertRequest(BaseModel):
    channel: Literal["email", "ntfy", "windows_toast"]


@router.get("/settings")
def get_settings_api():
    return load_example("settings.json")


@router.put("/settings")
def put_settings_api():
    return load_example("settings.json")


async def _run_manual_eod_backfill() -> None:
    """
    Reuse the same backfill routine that runs on startup to check/produce EOD snapshots.
    Runs in a background task so the API call returns immediately.
    """
    try:
        log.info("manual_eod_backfill_begin")
        rc = await anyio.to_thread.run_sync(backfill_main, [])
        log.info("manual_eod_backfill_done", extra={"rc": rc})
    except Exception:
        log.exception("manual_eod_backfill_failed")


@router.post("/settings/run-eod")
async def trigger_daily_eod():
    try:
        asyncio.create_task(_run_manual_eod_backfill())
    except Exception:
        log.exception("manual_eod_backfill_schedule_failed")
        return {"status": "failed"}
    return {"status": "scheduled"}


@router.get("/settings/windows-toast")
def get_windows_toast_setting():
    """Return the in-process runtime flag for the Windows toast channel.

    Note: this is the *runtime* override. The channel still needs
    alerts.delivery.windows_toast.enabled=true in the YAML to ever fire.
    """
    return {"enabled": toast_get_runtime_enabled()}


@router.post("/settings/windows-toast")
def set_windows_toast_setting(payload: WindowsToastToggle):
    """Enable or disable Windows toast alerts at runtime.

    Body: {"enabled": true|false}

    If ``enabled`` is omitted, the flag is toggled. The change is
    in-process only — to persist across restarts, flip
    alerts.delivery.windows_toast.enabled in alerts.yaml.
    """
    current = toast_get_runtime_enabled()
    target = (not current) if payload.enabled is None else bool(payload.enabled)
    new_val = toast_set_runtime_enabled(target)
    return {"enabled": new_val, "previous": current}


# ---------------- Test-alert endpoint ----------------
# The Settings page exposes one button per channel. Each click POSTs here with
# the channel name; we build a fake event, synthesize a "this is a test" title
# and body, and invoke that channel's sender directly. We intentionally
# bypass the full dedupe/cooldown/rate-limit pipeline because a test button
# should always fire, regardless of whether a real alert for TEST symbol was
# recently sent. We also skip the DB write so test alerts don't show up in
# the alert_events history.

def _build_test_payload(channel: str) -> Dict[str, str]:
    ts_local = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S %Z")
    return {
        "title": f"[TEST] Momentum Alert via {channel}",
        "body": (
            "This is a test notification fired from the Settings page.\n"
            f"Channel: {channel}\n"
            f"Time: {ts_local}\n"
            "If you are seeing this, the channel is configured correctly."
        ),
    }


def _send_test_email(cfg) -> Dict[str, Any]:
    email_cfg = cfg.alerts.delivery.email
    if not email_cfg.enabled:
        return {
            "status": "SKIPPED",
            "reason": "email channel disabled in alerts.yaml "
                      "(alerts.delivery.email.enabled=false)",
        }
    smtp = email_cfg.smtp
    recipients = [r for r in (email_cfg.defaults.to or []) if r]
    if not recipients:
        return {
            "status": "SKIPPED",
            "reason": "no email recipients configured (set ALERT_EMAIL_TO_1 "
                      "env var or alerts.delivery.email.defaults.to)",
        }
    chan_cfg = {
        "enabled": True,
        "smtp": {
            "host": smtp.host,
            "port": smtp.port,
            "username": smtp.username,
            "password": smtp.password,
            "use_tls": smtp.use_tls,
            "from_addr": smtp.from_addr,
            "from_name": smtp.from_name,
        },
        "to": recipients,
    }
    fake_event = {
        "id": 0,
        "rule_code": "TEST_ALERT",
        "symbol": "TEST",
        "severity": "INFO",
    }
    content = _build_test_payload("email")
    result = send_email_channel(fake_event, content, chan_cfg)
    return {
        "status": result.status,
        "code": result.response_code,
        "meta": result.response_meta,
        "to": recipients,
    }


def _send_test_ntfy(cfg) -> Dict[str, Any]:
    ntfy = cfg.alerts.delivery.ntfy
    if not ntfy.enabled:
        return {
            "status": "SKIPPED",
            "reason": "ntfy channel disabled in alerts.yaml "
                      "(alerts.delivery.ntfy.enabled=false)",
        }
    topic = ntfy.topic_high or ntfy.topic_low
    if not topic:
        return {
            "status": "SKIPPED",
            "reason": "ntfy has no topic configured (set NTFY_TOPIC_HIGH "
                      "or NTFY_TOPIC_LOW)",
        }
    chan_cfg = {
        "enabled": True,
        "server": ntfy.server,
        "topic": topic,
    }
    fake_event = {
        "id": 0,
        "rule_code": "TEST_ALERT",
        "symbol": "TEST",
        "severity": "INFO",
    }
    content = _build_test_payload("ntfy")
    result = send_ntfy_channel(fake_event, content, chan_cfg)
    return {
        "status": result.status,
        "code": result.response_code,
        "meta": result.response_meta,
        "topic": topic,
        "server": ntfy.server,
    }


def _send_test_windows_toast(cfg) -> Dict[str, Any]:
    toast_cfg = cfg.alerts.delivery.windows_toast
    if not toast_cfg.enabled:
        return {
            "status": "SKIPPED",
            "reason": "windows_toast channel disabled in alerts.yaml "
                      "(alerts.delivery.windows_toast.enabled=false)",
        }
    if not toast_get_runtime_enabled():
        return {
            "status": "SKIPPED",
            "reason": "windows_toast runtime toggle is OFF — enable it first "
                      "via POST /api/v1/settings/windows-toast",
        }
    chan_cfg = {
        "enabled": True,
        "play_sound": bool(toast_cfg.play_sound),
        "sound_alias": toast_cfg.sound_alias,
        "app_id": toast_cfg.app_id,
    }
    fake_event = {
        "id": 0,
        "rule_code": "TEST_ALERT",
        "symbol": "TEST",
        "severity": "INFO",
    }
    content = _build_test_payload("windows_toast")
    result = send_windows_toast_channel(fake_event, content, chan_cfg)
    return {
        "status": result.status,
        "code": result.response_code,
        "meta": result.response_meta,
    }


@router.post("/settings/test-alert")
def fire_test_alert(payload: TestAlertRequest):
    """Fire a single test alert through the requested channel.

    Body: ``{"channel": "email" | "ntfy" | "windows_toast"}``

    The test alert is a fake event with symbol=TEST and rule_code=TEST_ALERT;
    it is NOT persisted to alert_events and does NOT go through the dedupe,
    cooldown, or rate-limit gates, so repeated clicks always fire.
    """
    try:
        cfg = config_module.load()
    except Exception as exc:
        log.exception("test_alert config load failed")
        raise HTTPException(status_code=500, detail=f"config load failed: {exc}")

    ch = payload.channel
    log.info("test_alert requested channel=%s", ch)
    try:
        if ch == "email":
            data = _send_test_email(cfg)
        elif ch == "ntfy":
            data = _send_test_ntfy(cfg)
        elif ch == "windows_toast":
            data = _send_test_windows_toast(cfg)
        else:  # pragma: no cover - pydantic Literal already guards this
            raise HTTPException(status_code=400, detail=f"unknown channel: {ch}")
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("test_alert channel=%s raised", ch)
        raise HTTPException(status_code=500, detail=repr(exc))

    data["channel"] = ch
    log.info("test_alert result channel=%s status=%s", ch, data.get("status"))
    return data
