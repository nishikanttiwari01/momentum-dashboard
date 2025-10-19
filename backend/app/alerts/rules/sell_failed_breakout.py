from __future__ import annotations
from typing import Optional
from ..base import EvalContext, EvalResult
from ..types import Severity

CODE = "SELL_FAILED_BREAKOUT"

def evaluate(ctx: EvalContext, symbol: str) -> Optional[EvalResult]:
    return EvalResult(triggered=True, severity=Severity.WARN, context_json={}, details_json={})
