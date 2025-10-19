from __future__ import annotations
from typing import Optional
from ..base import EvalContext, EvalResult
from ..types import Severity

CODE = "SELL_STOP_NOW"

def evaluate(ctx: EvalContext, symbol: str) -> Optional[EvalResult]:
    stop = ctx.metric(symbol, "position_stop")
    return EvalResult(
        triggered=True,
        severity=Severity.CRITICAL,
        context_json={"position_ctx.stop": stop},
        details_json={}
    )
