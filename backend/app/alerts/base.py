from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Callable
from datetime import datetime, date
from .types import Mode, Severity

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
            return v if v is not None else default
        except Exception:
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
        raise NotImplementedError("implement in rule module")
