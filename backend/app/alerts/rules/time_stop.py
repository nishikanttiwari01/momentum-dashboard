from __future__ import annotations
from typing import Optional
import logging
from ..base import EvalContext, EvalResult
from ..types import Severity

log = logging.getLogger(__name__)

CODE = "TIME_STOP"

def evaluate(ctx: EvalContext, symbol: str) -> Optional[EvalResult]:
    log.debug("Evaluating %s for symbol=%s", CODE, symbol)
    d = ctx.metric(symbol, "days_since_entry")
    s = ctx.metric(symbol, "score")
    result = EvalResult(
        triggered=True,
        severity=Severity.INFO,
        context_json={"days_since_entry": d, "score": s},
        details_json={}
    )
    log.debug("%s evaluation context=%s", CODE, result.context_json)
    return result
