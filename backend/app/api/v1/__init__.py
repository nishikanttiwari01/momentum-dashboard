# backend/app/api/v1/__init__.py
from __future__ import annotations

# Re-export router modules for easy import in app.main
from . import health
from . import data_health
from . import portfolio
from . import us_portfolio
from . import news_relevant
from . import screener
from . import instruments
from . import alerts
from . import history
from . import settings

# Phase 9 additions
from . import runs
from . import scan
from . import positions
from . import momentum
from . import candidate_pool
from . import simulator

__all__: list[str] = [
    "health",
    "data_health",
    "portfolio",
    "us_portfolio",
    "news_relevant",
    "screener",
    "instruments",
    "alerts",
    "history",
    "settings",
    "runs",
    "scan",
    "positions",
    "momentum",
    "candidate_pool",
    "simulator",
]
