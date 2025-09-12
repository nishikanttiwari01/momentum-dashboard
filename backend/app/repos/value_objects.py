# backend/app/repos/value_objects.py
from __future__ import annotations

# Re-export the VO so tests can import from app.repos.value_objects
from .interfaces.base import AlertRuleVO

__all__ = ["AlertRuleVO"]
