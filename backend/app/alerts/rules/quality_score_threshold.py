from __future__ import annotations
from typing import Optional
from ..base import EvalContext, EvalResult
from ..types import Severity

CODE = "QUALITY_SCORE_THRESHOLD"

def evaluate(ctx: EvalContext, symbol: str) -> Optional[EvalResult]:
    s = ctx.metric(symbol, "score")
    return EvalResult(triggered=True, severity=Severity.INFO, context_json={"score": s}, details_json={})
