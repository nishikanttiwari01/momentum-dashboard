from __future__ import annotations
from typing import Optional
import logging
from ..base import EvalContext, EvalResult
from ..types import Severity

log = logging.getLogger(__name__)

CODE = "BUY_BREAKOUT"

def evaluate(ctx: EvalContext, symbol: str) -> Optional[EvalResult]:
    log.debug("Evaluating %s for symbol=%s", CODE, symbol)
    score = ctx.metric(symbol, "score")
    pivot_clear_pct = ctx.metric(symbol, "pivot_clear_pct")
    relvol20 = ctx.metric(symbol, "relvol20")
    severity = Severity(ctx.item_cfg.get("severity", ctx.defaults.get("severity", "INFO")))
    result = EvalResult(
        triggered=True,
        severity=severity,
        context_json={
            "score": score,
            "pivot_clear_pct": pivot_clear_pct,
            "relvol20": relvol20,
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
