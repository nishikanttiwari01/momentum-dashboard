from __future__ import annotations
from typing import Optional
import logging
from ..base import EvalContext, EvalResult
from ..types import Severity

log = logging.getLogger(__name__)

CODE = "HOLD_CAUTION"

def evaluate(ctx: EvalContext, symbol: str) -> Optional[EvalResult]:
    log.debug("Evaluating %s for symbol=%s", CODE, symbol)
    result = EvalResult(
        triggered=True,
        severity=Severity.INFO,
        context_json={},
        details_json={}
    )
    log.debug("%s evaluation produced default context", CODE)
    return result
