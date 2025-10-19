from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Callable
from datetime import datetime, date
import logging
from .types import Mode, Severity

log = logging.getLogger(__name__)

MetricGetter = Callable[[str, str], Any]  # (symbol, metric_name) -> value

@dataclass
class EvalContext:
    # Required runtime inputs
    mode: Mode
    trading_date: date
    now_utc: datetime
    profile: Optional[str]
    config_version: Optional[int]

    # Loaded YAML (already merged in config)
    defaults: Dict[str, Any]
    thresholds: Dict[str, Any]
    item_cfg: Dict[str, Any]

    # Data access (supplied by caller)
    metric_getter: MetricGetter

    # Runner metadata
    triggered_by: str = "SCHEDULE"

    # Helpers
    def metric(self, symbol: str, name: str, default: Any = None) -> Any:
        try:
            v = self.metric_getter(symbol, name)
            if v is None:
                log.debug("Metric %s for %s missing, returning default=%r", name, symbol, default)
            return v if v is not None else default
        except Exception:
            log.exception("Metric getter raised for symbol=%s metric=%s; returning default=%r", symbol, name, default)
            return default

@dataclass
class EvalResult:
    # core
    triggered: bool
    severity: Severity
    context_json: Dict[str, Any] = field(default_factory=dict)
    details_json: Dict[str, Any] = field(default_factory=dict)

    # optional overrides
    next_action_code: Optional[str] = None
    channels_override: Optional[Dict[str, Any]] = None

class BaseRule:
    CODE = "GENERIC"

    def evaluate(self, ctx: EvalContext, symbol: str) -> Optional[EvalResult]:
        log.debug("BaseRule.evaluate called for %s without implementation", self.__class__.__name__)
        raise NotImplementedError("implement in rule module")
