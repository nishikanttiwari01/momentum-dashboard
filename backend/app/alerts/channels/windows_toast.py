"""Windows desktop toast + sound alert channel.

Fires a Windows 10/11 toast notification and plays a short chime whenever
an alert is routed through this channel. Lives alongside the ntfy / email /
webhook channels and follows the same sender-func contract: a pure function
that takes (event, content, chan_cfg) and returns a :class:`DeliveryResult`.

Design goals
------------
- **No pip dependencies.** The toast is fired via PowerShell's native
  :code:`Windows.UI.Notifications` API; the sound via Python's stdlib
  :mod:`winsound`. Works out of the box on Windows 10 / 11.
- **Graceful on non-Windows.** On Linux / macOS the channel returns
  :code:`SKIPPED` rather than failing — useful for dev environments.
- **Runtime toggle.** Channel can be disabled at runtime via
  :func:`set_runtime_enabled` without restarting the app. The toggle is
  checked before the config-file :code:`enabled` flag is honored; the
  effective state is ``config_enabled AND runtime_enabled``.
- **Non-blocking.** PowerShell toast launch and sound playback are fired
  and we don't wait for the toast to auto-dismiss. Sound uses
  :code:`SND_ASYNC`.
"""
from __future__ import annotations

import logging
import os
import platform
import subprocess
import tempfile
import threading
from typing import Any, Dict

from .base import DeliveryResult

log = logging.getLogger(__name__)

# Module-level runtime override. Defaults to True so that once a user enables
# the channel in alerts.yaml it is actually on. Flipping this at runtime
# (e.g. from an API endpoint) lets the user silence desktop pings without
# restarting the backend.
_RUNTIME_ENABLED: bool = True
_RUNTIME_LOCK = threading.Lock()


def set_runtime_enabled(flag: bool) -> bool:
    """Enable or disable the channel at runtime.

    Returns the new effective runtime flag. Callers are expected to persist
    the value elsewhere if they want it to survive restarts — this module
    only holds it in memory.
    """
    global _RUNTIME_ENABLED
    with _RUNTIME_LOCK:
        _RUNTIME_ENABLED = bool(flag)
        log.info("windows_toast runtime flag set to %s", _RUNTIME_ENABLED)
        return _RUNTIME_ENABLED


def get_runtime_enabled() -> bool:
    with _RUNTIME_LOCK:
        return _RUNTIME_ENABLED


def _is_windows() -> bool:
    return platform.system() == "Windows" or os.name == "nt"


def _play_sound(sound_alias: str = "SystemAsterisk") -> None:
    """Play a short Windows system sound asynchronously.

    Falls back silently if :mod:`winsound` is unavailable (non-Windows or
    embedded runtime). Uses :code:`SND_ASYNC` so the function returns
    immediately; the sound plays in the OS mixer thread.
    """
    if not _is_windows():
        return
    try:
        import winsound  # type: ignore[import-not-found]

        winsound.PlaySound(sound_alias, winsound.SND_ALIAS | winsound.SND_ASYNC)
    except Exception as exc:  # pragma: no cover - best-effort
        log.debug("windows_toast: sound playback skipped: %r", exc)


def _show_toast(title: str, body: str) -> Dict[str, Any]:
    """Fire a Windows toast via a temp .ps1 file (BurntToast with WinRT fallback).

    Writing a .ps1 file and using -File avoids all command-line escaping and
    stdin/mode quirks. The script tries BurntToast first (registered AppId
    guarantees banner popup), then falls back to the raw WinRT API with
    PowerShell's own registered AppId. Returns full stderr on failure so the
    caller can surface it in logs and the API response.
    """
    if not _is_windows():
        return {"reason": "NOT_WINDOWS", "platform": platform.system()}

    safe_title = (title or "")[:120].replace("'", "''")
    safe_body = (body or "")[:300].replace("'", "''")

    # Build the script as plain string concatenation to keep curly braces
    # for PowerShell blocks unambiguous (no f-string {{ }} confusion).
    ps_lines = [
        f"$t = '{safe_title}'",
        f"$b = '{safe_body}'",
        "$method = ''",
        "try {",
        "    Import-Module BurntToast -ErrorAction Stop",
        "    New-BurntToastNotification -Text $t, $b",
        "    $method = 'burnttoast'",
        "} catch {",
        # WinRT fallback: use PowerShell's own registered AppId so Windows
        # allows the banner without needing BurntToast installed.
        "    $appId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe'",
        "    [Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime] | Out-Null",
        "    [Windows.Data.Xml.Dom.XmlDocument,Windows.Data.Xml.Dom.XmlDocument,ContentType=WindowsRuntime] | Out-Null",
        "    $xml  = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent(",
        "                [Windows.UI.Notifications.ToastTemplateType]::ToastText02)",
        "    $nodes = $xml.GetElementsByTagName('text')",
        "    [void]$nodes.Item(0).AppendChild($xml.CreateTextNode($t))",
        "    [void]$nodes.Item(1).AppendChild($xml.CreateTextNode($b))",
        "    $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)",
        "    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show($toast)",
        "    $method = 'winrt'",
        "}",
        "Write-Output $method",
    ]
    script = "\r\n".join(ps_lines)

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".ps1", delete=False, encoding="utf-8"
        ) as fh:
            fh.write(script)
            tmp_path = fh.name

        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", tmp_path],
            capture_output=True,
            text=True,
            timeout=15,
        )

        if proc.returncode == 0:
            method = (proc.stdout or "").strip() or "unknown"
            return {"returncode": 0, "method": method}

        stderr = (proc.stderr or "").strip()[:500]
        log.warning("windows_toast failed rc=%s stderr=%s", proc.returncode, stderr)
        return {"returncode": proc.returncode, "stderr": stderr}

    except FileNotFoundError:
        return {"reason": "POWERSHELL_MISSING"}
    except subprocess.TimeoutExpired:
        return {"reason": "POWERSHELL_TIMEOUT"}
    except Exception as exc:  # pragma: no cover
        return {"reason": "POWERSHELL_ERROR", "error": repr(exc)}
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def send(event: Dict[str, Any], content: Dict[str, str], chan_cfg: Dict[str, Any]) -> DeliveryResult:
    """Dispatcher-compatible sender.

    Config shape (read from ``chan_cfg``, already resolved by the router):
        enabled: bool
        play_sound: bool (default True)
        sound_alias: str (default "SystemAsterisk"; see winsound aliases)
        app_id: str (default "Momentum Alerts")
    """
    if not chan_cfg.get("enabled", False):
        return DeliveryResult(status="SKIPPED", response_meta={"reason": "DISABLED"})

    if not get_runtime_enabled():
        return DeliveryResult(
            status="SKIPPED",
            response_meta={"reason": "RUNTIME_DISABLED"},
        )

    if not _is_windows():
        # Soft-skip so dev machines (Linux/macOS CI) don't turn alerts red.
        return DeliveryResult(
            status="SKIPPED",
            response_meta={"reason": "NOT_WINDOWS", "platform": platform.system()},
        )

    title = content.get("title") or event.get("rule_code", "Alert")
    body = content.get("body") or ""

    meta = _show_toast(title, body)

    if chan_cfg.get("play_sound", True):
        alias = str(chan_cfg.get("sound_alias") or "SystemAsterisk")
        _play_sound(alias)

    if meta.get("returncode") == 0:
        log.info(
            "windows_toast delivered event_id=%s title=%r",
            event.get("id"),
            title,
        )
        return DeliveryResult(status="SENT", response_code=0, response_meta=meta)

    log.warning(
        "windows_toast failed event_id=%s meta=%s",
        event.get("id"),
        meta,
    )
    return DeliveryResult(status="FAILED", response_meta=meta)
