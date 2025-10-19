from __future__ import annotations
from typing import Optional
import logging
from ..base import EvalContext, EvalResult
from ..types import Severity

log = logging.getLogger(__name__)

CODE = "BUY_STARTER"

def evaluate(ctx: EvalContext, symbol: str) -> Optional[EvalResult]:
    log.debug("Evaluating %s for symbol=%s", CODE, symbol)
    score = ctx.metric(symbol, "intraday_score")
    result = EvalResult(
        triggered=True,
        severity=Severity.INFO,
        context_json={
            "score": score,
            "persistence_ok": ctx.metric(symbol, "persistence_ok"),
            "next_action_code": "BUY_BREAKOUT",
        },
        details_json={}
    )
    log.debug("%s evaluation context=%s", CODE, result.context_json)
    return result
