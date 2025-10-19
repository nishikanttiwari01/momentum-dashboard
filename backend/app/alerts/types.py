from __future__ import annotations
from enum import Enum
import logging

log = logging.getLogger(__name__)

class Mode(str, Enum):
    EOD = "EOD"
    INTRADAY = "INTRADAY"

class Severity(str, Enum):
    INFO = "INFO"
    WARN = "WARN"
    CRITICAL = "CRITICAL"

class Channel(str, Enum):
    NTFY = "ntfy"
    EMAIL = "email"
    WEBHOOK = "webhook"

class SendStatus(str, Enum):
    SENT = "SENT"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"

log.debug(
    "Alert types defined modes=%s severities=%s channels=%s statuses=%s",
    [m.value for m in Mode],
    [s.value for s in Severity],
    [c.value for c in Channel],
    [s.value for s in SendStatus],
)
