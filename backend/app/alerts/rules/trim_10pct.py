from __future__ import annotations
from typing import Optional
from ..base import EvalContext, EvalResult
from ..types import Severity

CODE = "TRIM_10PCT"

def evaluate(ctx: EvalContext, symbol: str) -> Optional[EvalResult]:
    g = ctx.metric(symbol, "unrealized_gain_pct")
    return EvalResult(
        triggered=True,
        severity=Severity.INFO,
        context_json={"unrealized_gain_pct": g},
        details_json={}
    )
