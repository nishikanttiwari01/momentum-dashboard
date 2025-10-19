from __future__ import annotations
from typing import Optional
from ..base import EvalContext, EvalResult
from ..types import Severity

CODE = "TIME_STOP"

def evaluate(ctx: EvalContext, symbol: str) -> Optional[EvalResult]:
    d = ctx.metric(symbol, "days_since_entry")
    s = ctx.metric(symbol, "score")
    return EvalResult(
        triggered=True,
        severity=Severity.INFO,
        context_json={"days_since_entry": d, "score": s},
        details_json={}
    )
