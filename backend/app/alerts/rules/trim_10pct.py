from __future__ import annotations
from typing import Optional
import logging
from ..base import EvalContext, EvalResult
from ..types import Severity

log = logging.getLogger(__name__)

CODE = "TRIM_10PCT"

def evaluate(ctx: EvalContext, symbol: str) -> Optional[EvalResult]:
    log.debug("Evaluating %s for symbol=%s", CODE, symbol)
    g = ctx.metric(symbol, "unrealized_gain_pct")
    result = EvalResult(
        triggered=True,
        severity=Severity.INFO,
        context_json={"unrealized_gain_pct": g},
        details_json={}
    )
    log.debug("%s evaluation context=%s", CODE, result.context_json)
    return result
