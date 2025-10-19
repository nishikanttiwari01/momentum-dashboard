from __future__ import annotations
from typing import Optional
from ..base import EvalContext, EvalResult
from ..types import Severity

CODE = "HOLD_TIGHT"

def evaluate(ctx: EvalContext, symbol: str) -> Optional[EvalResult]:
    return EvalResult(
        triggered=True,
        severity=Severity.INFO,
        context_json={},
        details_json={}
    )
