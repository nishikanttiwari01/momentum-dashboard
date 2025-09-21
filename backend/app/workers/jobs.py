# backend/app/workers/jobs.py
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

# Reuse your existing settings loader (YAML-first config)
from app.core.config import get_settings  # returns Settings model
# Post-scan alert evaluator (Momentum ≥ threshold, once-per-day per ticker)
from app.services.alerts import evaluate_momentum_crossups

logger = logging.getLogger(__name__)


def post_scan_jobs(run_id: Optional[str]) -> Dict[str, Any]:
    """
    Run lightweight, idempotent post-scan tasks for a completed screening run.

    Currently:
      - Evaluate Momentum ≥ threshold cross-up and send alerts (Telegram + Desktop toast),
        enforcing "once per ticker per local day" for this rule.

    Returns a small summary dict (counts) for logging/metrics.
    """
    # Get YAML-driven settings; the alerts service tolerates either a dict or the model.
    settings = get_settings()
    settings_payload: Dict[str, Any]
    try:
        # pydantic BaseModel supports .model_dump() (v2) or .dict() (v1)
        settings_payload = settings.model_dump()  # type: ignore[attr-defined]
    except Exception:
        try:
            settings_payload = settings.dict()  # type: ignore[attr-defined]
        except Exception:
            # Fallback: pass through the object (alerts service is defensive)
            settings_payload = {}  # minimal; the service will use its defaults

    fired = 0
    try:
        fired = evaluate_momentum_crossups(run_id, settings_payload)
        logger.info("post_scan_jobs: alerts fired=%s run_id=%s", fired, run_id)
    except Exception as e:
        # Never fail the job chain due to notifications—just log.
        logger.exception("post_scan_jobs: alert evaluation failed for run_id=%s: %s", run_id, e)

    return {"alerts_fired": fired}


# Optional: alias if you prefer a more generic name at call sites.
run_post_scan_jobs = post_scan_jobs

if __name__ == "__main__":
    # Manual test runner:
    import os, sys
    rid = os.getenv("RUN_ID") or (sys.argv[1] if len(sys.argv) > 1 else None)
    out = post_scan_jobs(rid)
    print(out)
