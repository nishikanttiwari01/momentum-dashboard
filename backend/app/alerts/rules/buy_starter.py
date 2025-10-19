from __future__ import annotations
from typing import Optional
from ..base import EvalContext, EvalResult
from ..types import Severity

CODE = "BUY_STARTER"

def evaluate(ctx: EvalContext, symbol: str) -> Optional[EvalResult]:
    score = ctx.metric(symbol, "intraday_score")
    return EvalResult(
        triggered=True,
        severity=Severity.INFO,
        context_json={
            "score": score,
            "persistence_ok": ctx.metric(symbol, "persistence_ok"),
            "next_action_code": "BUY_BREAKOUT",
        },
        details_json={}
    )
