from __future__ import annotations
from datetime import datetime, time
from zoneinfo import ZoneInfo
from typing import Tuple
from .types import Mode

def is_within_trading_window(now_utc: datetime, tz_str: str, start_hhmm: str, end_hhmm: str) -> bool:
    tz = ZoneInfo(tz_str)
    local = now_utc.astimezone(tz)
    sh, sm = map(int, start_hhmm.split(":"))
    eh, em = map(int, end_hhmm.split(":"))
    return time(sh, sm) <= local.time() <= time(eh, em)

def compute_mode(now_utc: datetime, tz_str: str, close_hhmm: str, eod_delay_minutes: int) -> Mode:
    tz = ZoneInfo(tz_str)
    local = now_utc.astimezone(tz)
    ch, cm = map(int, close_hhmm.split(":"))
    close_dt = local.replace(hour=ch, minute=cm, second=0, microsecond=0)
    if (local - close_dt).total_seconds() >= eod_delay_minutes * 60:
        return Mode.EOD
    return Mode.INTRADAY

def compute_intraday_bucket(now_utc: datetime, tz_str: str, open_hhmm: str, bar_minutes: int) -> tuple[int, str]:
    tz = ZoneInfo(tz_str)
    local = now_utc.astimezone(tz)
    oh, om = map(int, open_hhmm.split(":"))
    open_dt = local.replace(hour=oh, minute=om, second=0, microsecond=0)
    mins = int(max(0, (local - open_dt).total_seconds() // 60))
    bucket = mins // max(1, bar_minutes)
    label = f"{local.hour:02d}{local.minute:02d}"
    return bucket, label
