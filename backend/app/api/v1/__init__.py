# backend/app/api/v1/__init__.py
from __future__ import annotations

# Re-export router modules for easy import in app.main
from . import health
from . import screener
from . import instruments
from . import alerts
from . import history
from . import settings

# Phase 9 additions
from . import runs
from . import scan
from . import positions

__all__: list[str] = [
    "health",
    "screener",
    "instruments",
    "alerts",
    "history",
    "settings",
    "runs",
    "scan",
    "positions",
]
