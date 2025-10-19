from __future__ import annotations
from enum import Enum

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
