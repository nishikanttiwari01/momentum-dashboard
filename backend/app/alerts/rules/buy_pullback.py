from __future__ import annotations
from typing import Optional
import logging
from ..base import EvalContext, EvalResult
from ..types import Severity

log = logging.getLogger(__name__)

CODE = "BUY_PULLBACK"

def evaluate(ctx: EvalContext, symbol: str) -> Optional[EvalResult]:
    log.debug("Evaluating %s for symbol=%s", CODE, symbol)
    score = ctx.metric(symbol, "score")
    severity = Severity(ctx.item_cfg.get("severity", ctx.defaults.get("severity", "INFO")))
    result = EvalResult(
        triggered=True,
        severity=severity,
        context_json={
            "score": score,
            "ema10_pullback_zone": ctx.metric(symbol, "ema10_pullback_zone"),
            "next_action_code": ctx.metric(symbol, "next_action_code"),
        },
        details_json={}
    )
    log.debug(
        "%s evaluation produced severity=%s context=%s",
        CODE,
        severity,
        result.context_json,
    )
    return result
