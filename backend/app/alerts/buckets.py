from __future__ import annotations
from datetime import datetime, time
from zoneinfo import ZoneInfo
from typing import Tuple
import logging
from .types import Mode

log = logging.getLogger(__name__)

def is_within_trading_window(now_utc: datetime, tz_str: str, start_hhmm: str, end_hhmm: str) -> bool:
    tz = ZoneInfo(tz_str)
    local = now_utc.astimezone(tz)
    sh, sm = map(int, start_hhmm.split(":"))
    eh, em = map(int, end_hhmm.split(":"))
    within = time(sh, sm) <= local.time() <= time(eh, em)
    log.debug(
        "Trading window check tz=%s local_time=%s window=%s-%s => %s",
        tz_str,
        local.time(),
        start_hhmm,
        end_hhmm,
        within,
    )
    return within

def compute_mode(now_utc: datetime, tz_str: str, close_hhmm: str, eod_delay_minutes: int) -> Mode:
    tz = ZoneInfo(tz_str)
    local = now_utc.astimezone(tz)
    ch, cm = map(int, close_hhmm.split(":"))
    close_dt = local.replace(hour=ch, minute=cm, second=0, microsecond=0)
    seconds_since_close = (local - close_dt).total_seconds()
    if seconds_since_close >= eod_delay_minutes * 60:
        log.debug(
            "Mode computed as EOD tz=%s local=%s close=%s delay=%s elapsed=%s",
            tz_str,
            local,
            close_dt,
            eod_delay_minutes,
            seconds_since_close,
        )
        return Mode.EOD
    log.debug(
        "Mode computed as INTRADAY tz=%s local=%s close=%s delay=%s elapsed=%s",
        tz_str,
        local,
        close_dt,
        eod_delay_minutes,
        seconds_since_close,
    )
    return Mode.INTRADAY

def compute_intraday_bucket(now_utc: datetime, tz_str: str, open_hhmm: str, bar_minutes: int) -> tuple[int, str]:
    tz = ZoneInfo(tz_str)
    local = now_utc.astimezone(tz)
    oh, om = map(int, open_hhmm.split(":"))
    open_dt = local.replace(hour=oh, minute=om, second=0, microsecond=0)
    mins = int(max(0, (local - open_dt).total_seconds() // 60))
    bucket = mins // max(1, bar_minutes)
    label = f"{local.hour:02d}{local.minute:02d}"
    log.debug(
        "Intraday bucket tz=%s local=%s open=%s bar=%s minutes_since_open=%s bucket=%s label=%s",
        tz_str,
        local,
        open_dt,
        bar_minutes,
        mins,
        bucket,
        label,
    )
    return bucket, label
