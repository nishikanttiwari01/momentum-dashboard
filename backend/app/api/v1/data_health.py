# backend/app/api/v1/data_health.py
"""Data-health endpoint: reports how fresh every dataset actually is.

The dashboard shows these timestamps so stale/broken feeds are visible
instead of silently rendering old (or no) data.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter

from app.core import config as app_config

router = APIRouter(tags=["Health"])


def _latest_mtime(root: Path) -> Optional[datetime]:
    """Newest file mtime under root (walk capped for safety)."""
    if not root.exists():
        return None
    newest: Optional[float] = None
    count = 0
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            count += 1
            if count > 20000:
                break
            try:
                m = os.path.getmtime(os.path.join(dirpath, fn))
            except OSError:
                continue
            if newest is None or m > newest:
                newest = m
        if count > 20000:
            break
    if newest is None:
        return None
    return datetime.fromtimestamp(newest, tz=timezone.utc)


def _dataset_status(name: str, root: Path) -> Dict[str, Any]:
    mtime = _latest_mtime(root)
    age_hours: Optional[float] = None
    if mtime is not None:
        age_hours = round((datetime.now(timezone.utc) - mtime).total_seconds() / 3600.0, 1)
    return {
        "name": name,
        "exists": root.exists(),
        "last_updated": mtime.isoformat() if mtime else None,
        "age_hours": age_hours,
    }


@router.get("/health/data")
def data_health():
    cfg = app_config.load()
    parquet_root = Path(cfg.storage.parquet_root or "./backend/parquet")

    datasets: List[Dict[str, Any]] = [
        _dataset_status("prices", parquet_root / "prices"),
        _dataset_status("scores", parquet_root / "scores"),
        _dataset_status("indicators", parquet_root / "indicators"),
        _dataset_status("news", parquet_root / "news"),
        _dataset_status("universe", parquet_root / "universe"),
    ]

    pool_info: Dict[str, Any] = {"active": None, "stale": None, "oldest_age_days": None}
    try:
        from app.core.db import get_session
        from app.repos.sql.candidate_pool_repo import CandidatePoolRepo

        gen = get_session()
        session = next(gen)
        try:
            repo = CandidatePoolRepo(session=session)
            rows = repo.list_entries(active_only=True)
            today = datetime.now(timezone.utc).date()
            max_age = cfg.candidate_pool.exit_rules.max_age_days or 0
            ages: List[int] = []
            for r in rows:
                added = r.get("added_date")
                if isinstance(added, date):
                    ages.append((today - added).days)
            pool_info = {
                "active": len(rows),
                "stale": sum(1 for a in ages if max_age and a > max_age),
                "oldest_age_days": max(ages) if ages else None,
            }
        finally:
            gen.close()
    except Exception:
        pass

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "adapter": getattr(cfg.data, "adapter", None),
        "news_enabled": bool(getattr(cfg.news, "enabled", False)),
        "timezone": getattr(cfg.app, "timezone", None),
        "datasets": datasets,
        "candidate_pool": pool_info,
    }
