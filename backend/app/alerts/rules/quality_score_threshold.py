from __future__ import annotations
from typing import Optional
import logging
from ..base import EvalContext, EvalResult
from ..types import Severity

log = logging.getLogger(__name__)

CODE = "QUALITY_SCORE_THRESHOLD"

def evaluate(ctx: EvalContext, symbol: str) -> Optional[EvalResult]:
    log.debug("Evaluating %s for symbol=%s", CODE, symbol)
    s = ctx.metric(symbol, "score")
    result = EvalResult(triggered=True, severity=Severity.INFO, context_json={"score": s}, details_json={})
    log.debug("%s evaluation context=%s", CODE, result.context_json)
    return result
