from __future__ import annotations
from typing import Optional
from ..base import EvalContext, EvalResult
from ..types import Severity

CODE = "EUPHORIA_EXIT"

def evaluate(ctx: EvalContext, symbol: str) -> Optional[EvalResult]:
    rsi = ctx.metric(symbol, "rsi14")
    return EvalResult(triggered=True, severity=Severity.INFO, context_json={"rsi14": rsi}, details_json={})
