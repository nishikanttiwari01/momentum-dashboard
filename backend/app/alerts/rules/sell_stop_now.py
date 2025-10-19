from __future__ import annotations
from typing import Optional
import logging
from ..base import EvalContext, EvalResult
from ..types import Severity

log = logging.getLogger(__name__)

CODE = "SELL_STOP_NOW"

def evaluate(ctx: EvalContext, symbol: str) -> Optional[EvalResult]:
    log.debug("Evaluating %s for symbol=%s", CODE, symbol)
    stop = ctx.metric(symbol, "position_stop")
    result = EvalResult(
        triggered=True,
        severity=Severity.CRITICAL,
        context_json={"position_ctx.stop": stop},
        details_json={}
    )
    log.debug("%s evaluation context=%s", CODE, result.context_json)
    return result
