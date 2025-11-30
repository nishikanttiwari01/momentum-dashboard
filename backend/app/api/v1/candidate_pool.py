from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core import config as app_config
from app.repos.sql.candidate_pool_repo import CandidatePoolRepo
from app.services.candidate_pool_service import CandidatePoolService

# Generated models (contract-first)
from app.schemas.generated.models import CandidatePoolList  # type: ignore

try:
    from app.core.db import get_session  # must yield a Session
except Exception as e:
    get_session = None

router = APIRouter(prefix="/candidate-pool", tags=["Screener"])


def _require_session():
    if get_session is None:
        raise HTTPException(status_code=503, detail="DB not initialized")
    return get_session


@router.get("", response_model=CandidatePoolList)
def list_candidate_pool(s: Session = Depends(_require_session())):
    cfg = app_config.load()
    repo = CandidatePoolRepo(session=s)
    service = CandidatePoolService(repo=repo, cfg=cfg.candidate_pool, strategy=cfg.strategy)

    now = datetime.now(timezone.utc)
    trading_day = now.date()
    rows = repo.list_entries(active_only=True)

    entries = []
    for row in rows:
        entry = service._entry_from_repo(row, now)  # type: ignore[attr-defined]
        checks, notes = service._exit_checks(entry, trading_day)  # type: ignore[attr-defined]
        entry.exit_checks = checks
        entry.reasons = notes
        entry.stale = False
        entries.append(entry)

    ranked = service._rank_entries(entries)  # type: ignore[attr-defined]
    ranked.sort(
        key=lambda e: (
            e.rank_ord if e.rank_ord is not None else 1_000_000,
            -(e.rank_score or 0.0),
            e.symbol,
        )
    )

    items: List[dict] = []
    for idx, entry in enumerate(ranked, start=1):
        entry.rank_ord = entry.rank_ord or idx
        items.append(service.serialize_entry(entry, is_top=idx == 1))

    as_of = next(
        (r.get("last_seen_as_of") or r.get("added_as_of") for r in rows if r.get("last_seen_as_of") or r.get("added_as_of")),
        None,
    )

    return CandidatePoolList(
        max_size=cfg.candidate_pool.max_size,
        run_id=None,
        as_of=as_of,
        generated_at=now.isoformat(),
        items=items,
    )
