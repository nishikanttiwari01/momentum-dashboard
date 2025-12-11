#backend/app/api/v1/settings.py
import asyncio
import logging

import anyio
from fastapi import APIRouter

from app.cli.backfill import main as backfill_main
from ._examples import load_example

router = APIRouter()
log = logging.getLogger(__name__)


@router.get("/settings")
def get_settings_api():
    return load_example("settings.json")


@router.put("/settings")
def put_settings_api():
    return load_example("settings.json")


async def _run_manual_eod_backfill() -> None:
    """
    Reuse the same backfill routine that runs on startup to check/produce EOD snapshots.
    Runs in a background task so the API call returns immediately.
    """
    try:
        log.info("manual_eod_backfill_begin")
        rc = await anyio.to_thread.run_sync(backfill_main, [])
        log.info("manual_eod_backfill_done", extra={"rc": rc})
    except Exception:
        log.exception("manual_eod_backfill_failed")


@router.post("/settings/run-eod")
async def trigger_daily_eod():
    try:
        asyncio.create_task(_run_manual_eod_backfill())
    except Exception:
        log.exception("manual_eod_backfill_schedule_failed")
        return {"status": "failed"}
    return {"status": "scheduled"}
