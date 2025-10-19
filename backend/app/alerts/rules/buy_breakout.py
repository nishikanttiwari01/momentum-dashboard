from __future__ import annotations
from typing import Optional
from ..base import EvalContext, EvalResult
from ..types import Severity

CODE = "BUY_BREAKOUT"

def evaluate(ctx: EvalContext, symbol: str) -> Optional[EvalResult]:
    score = ctx.metric(symbol, "score")
    pivot_clear_pct = ctx.metric(symbol, "pivot_clear_pct")
    relvol20 = ctx.metric(symbol, "relvol20")
    return EvalResult(
        triggered=True,
        severity=Severity(ctx.item_cfg.get("severity", ctx.defaults.get("severity", "INFO"))),
        context_json={
            "score": score,
            "pivot_clear_pct": pivot_clear_pct,
            "relvol20": relvol20,
            "next_action_code": ctx.metric(symbol, "next_action_code"),
        },
        details_json={}
    )
