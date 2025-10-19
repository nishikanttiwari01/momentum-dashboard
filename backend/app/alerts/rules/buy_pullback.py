from __future__ import annotations
from typing import Optional
from ..base import EvalContext, EvalResult
from ..types import Severity

CODE = "BUY_PULLBACK"

def evaluate(ctx: EvalContext, symbol: str) -> Optional[EvalResult]:
    score = ctx.metric(symbol, "score")
    return EvalResult(
        triggered=True,
        severity=Severity(ctx.item_cfg.get("severity", ctx.defaults.get("severity", "INFO"))),
        context_json={
            "score": score,
            "ema10_pullback_zone": ctx.metric(symbol, "ema10_pullback_zone"),
            "next_action_code": ctx.metric(symbol, "next_action_code"),
        },
        details_json={}
    )
