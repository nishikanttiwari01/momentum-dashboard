# test_ntfy.py
import os
import requests

NTFY_SERVER = os.getenv("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
NTFY_TOPIC  = os.getenv("NTFY_TOPIC", "momentum-alerts-nishi")
NTFY_TOKEN  = os.getenv("NTFY_TOKEN", "")  # leave blank if not using auth

def notify(title: str, body: str, tags: str | None = None) -> None:
    url = f"{NTFY_SERVER}/{NTFY_TOPIC}"
    headers = {"Title": title, "Priority": "high"}
    if tags:
        headers["Tags"] = tags
    if NTFY_TOKEN:
        headers["Authorization"] = f"Bearer {NTFY_TOKEN}"

    r = requests.post(url, data=body.encode("utf-8"), headers=headers, timeout=8)
    r.raise_for_status()
    print("Sent:", r.json())

# === Quick test ===
if __name__ == "__main__":
    notify(
        title="Momentum Test Alert",
        body="Stock RELIANCE crossed momentum ≥ 80",
        tags="rocket,chart_with_upwards_trend"
    )
