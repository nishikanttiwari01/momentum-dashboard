from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.repos.models import PortfolioImport, PortfolioSnapshot
from app.schemas.wealth_portfolio import (
    ImportCommitResult,
    ImportPreview,
    SnapshotSummary,
    WealthSummary,
)
from app.services.wealth_import_service import (
    ImportBlocked,
    PreviewNotFound,
    import_service,
)
from app.services.wealth_summary_service import build_summary


MAX_WORKBOOK_BYTES = 20 * 1024 * 1024
router = APIRouter(prefix="/wealth-portfolio", tags=["Wealth Portfolio"])


@router.post("/imports/preview", response_model=ImportPreview)
async def preview_import(workbook: UploadFile = File(...)) -> ImportPreview:
    if not workbook.filename or not workbook.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="Only .xlsx workbooks are supported")
    payload = await workbook.read(MAX_WORKBOOK_BYTES + 1)
    if len(payload) > MAX_WORKBOOK_BYTES:
        raise HTTPException(status_code=413, detail="Workbook exceeds 20 MiB")
    if not payload:
        raise HTTPException(status_code=422, detail="Workbook is empty")
    try:
        return import_service.preview(payload, Path(workbook.filename).name)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Workbook could not be read") from exc


@router.post(
    "/imports/{preview_token}/commit",
    response_model=ImportCommitResult,
    status_code=status.HTTP_201_CREATED,
)
def commit_import(
    preview_token: str,
    response: Response,
    session: Session = Depends(get_session),
) -> ImportCommitResult:
    try:
        result = import_service.commit(session, preview_token)
    except PreviewNotFound as exc:
        raise HTTPException(status_code=404, detail="Import preview expired or was not found") from exc
    except ImportBlocked as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return result


@router.get("/snapshots/latest", response_model=SnapshotSummary)
def latest_snapshot(session: Session = Depends(get_session)) -> SnapshotSummary:
    row = session.execute(
        select(PortfolioSnapshot, PortfolioImport)
        .join(PortfolioImport, PortfolioSnapshot.import_id == PortfolioImport.id)
        .order_by(PortfolioSnapshot.as_of.desc(), PortfolioSnapshot.created_at.desc())
        .limit(1)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="No portfolio snapshot has been imported")
    snapshot, import_row = row
    return SnapshotSummary(
        snapshot_id=snapshot.id,
        as_of=snapshot.as_of,
        created_at=snapshot.created_at,
        source_filename=import_row.filename,
    )


@router.get("/summary", response_model=WealthSummary)
def summary(session: Session = Depends(get_session)) -> WealthSummary:
    return build_summary(session)
