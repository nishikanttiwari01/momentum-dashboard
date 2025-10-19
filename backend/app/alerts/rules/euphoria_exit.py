from __future__ import annotations
from typing import Optional
import logging
from ..base import EvalContext, EvalResult
from ..types import Severity

log = logging.getLogger(__name__)

CODE = "EUPHORIA_EXIT"

def evaluate(ctx: EvalContext, symbol: str) -> Optional[EvalResult]:
    log.debug("Evaluating %s for symbol=%s", CODE, symbol)
    rsi = ctx.metric(symbol, "rsi14")
    result = EvalResult(triggered=True, severity=Severity.INFO, context_json={"rsi14": rsi}, details_json={})
    log.debug("%s evaluation context=%s", CODE, result.context_json)
    return result
