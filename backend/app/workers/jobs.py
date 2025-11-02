from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def post_scan_jobs(run_id: Optional[str]) -> Dict[str, Any]:
    """
    Placeholder hook for post-scan background tasks.
    Alerts are emitted inline during screening (selection/sell engines),
    so this job currently logs completion and returns an empty summary.
    """
    try:
        logger.info("post_scan_jobs_start", extra={"run_id": run_id})
    except Exception:
        pass

    try:
        get_settings()
    except Exception as exc:
        try:
            logger.warning("post_scan_jobs_settings_failed", extra={"run_id": run_id, "error": str(exc)})
        except Exception:
            pass

    try:
        logger.info("post_scan_jobs_done", extra={"run_id": run_id})
    except Exception:
        pass

    return {"alerts_fired": 0}


run_post_scan_jobs = post_scan_jobs


if __name__ == "__main__":
    import os
    rid = os.getenv("RUN_ID")
    print(post_scan_jobs(rid))
