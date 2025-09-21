# app/notifs/telegram_toast.py
import os
import requests

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")
TG_CHAT_IDS = [cid.strip() for cid in os.getenv("TG_CHAT_IDS", "").split(",") if cid.strip()]
DESKTOP_TOAST = os.getenv("DESKTOP_TOAST", "1") == "1"

def _send_telegram(text: str) -> None:
    if not TG_BOT_TOKEN or not TG_CHAT_IDS:
        return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {"disable_web_page_preview": True}
    for cid in TG_CHAT_IDS:
        try:
            data = dict(payload, chat_id=cid, text=text)
            r = requests.post(url, json=data, timeout=8)
            r.raise_for_status()
        except Exception as e:
            print("[telegram] failed:", e)

def _send_desktop(title: str, body: str) -> None:
    if not DESKTOP_TOAST:
        return
    try:
        from plyer import notification  # pip install plyer
        notification.notify(title=title, message=body, timeout=8)
    except Exception as e:
        print("[toast] failed:", e)

def notify(
    *,
    title: str,
    body: str,
    severity: str = "info",
    dedupe_tag: str | None = None,  # handled upstream in service/state
    enable_telegram: bool = True,
    enable_desktop: bool = True,
) -> None:
    emoji = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "🛑"}.get(severity, "🔔")
    tg_text = f"{emoji} {title}\n{body}"
    if enable_telegram:
        _send_telegram(tg_text)
    if enable_desktop:
        _send_desktop(title, body)
