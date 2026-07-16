from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Path as ApiPath,
    Response,
    UploadFile,
    status,
)
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.repos.models import PortfolioImport, PortfolioSnapshot
from app.schemas.wealth_portfolio import (
    ImportCommitResult,
    ImportPreview,
    SnapshotSummary,
    WealthSummary,
    GoalConfigurationUpdate,
    PrimaryGoalResponse,
    FamilyPlanResponse,
    FamilyPlanUpdate,
    AnnualReviewOverrideUpdate,
    AnnualReviewResponse,
)
from app.services.annual_review_service import (
    delete_annual_review_overrides,
    get_annual_review,
    list_annual_reviews,
    save_annual_review_overrides,
)
from app.services.family_wealth_plan_service import (
    FamilyPlanNotFound,
    InvalidFamilyPlan,
    get_family_plan_response,
    restore_family_plan_defaults,
    save_family_plan,
)
from app.services.family_wealth_projection import UnsafeProjection
from app.services.wealth_import_service import (
    ImportBlocked,
    PreviewNotFound,
    import_service,
)
from app.services.wealth_summary_service import build_summary
from app.services.wealth_goal_service import (
    InvalidGoalConfiguration,
    PrimaryGoalNotFound,
    get_primary_goal_response,
    update_primary_goal,
)


MAX_WORKBOOK_BYTES = 20 * 1024 * 1024
router = APIRouter(prefix="/wealth-portfolio", tags=["Wealth Portfolio"])


def _goal_validation_error(exc: InvalidGoalConfiguration) -> RequestValidationError:
    return RequestValidationError(
        [
            {
                "type": exc.issue.error_type,
                "loc": ("body", *exc.issue.loc),
                "msg": exc.issue.message,
                "input": None,
                "ctx": {"error": exc},
            }
        ]
    )


def _family_validation_error(
    exc: InvalidFamilyPlan | ValidationError,
) -> RequestValidationError:
    if isinstance(exc, ValidationError):
        errors = [
            {**issue, "loc": ("body", *issue.get("loc", ()))}
            for issue in exc.errors()
        ]
    else:
        errors = [
            {
                "type": "family_plan_invalid",
                "loc": ("body",),
                "msg": "Family wealth plan configuration is invalid",
                "input": None,
            }
        ]
    return RequestValidationError(errors)


def _raise_family_plan_error(exc: Exception) -> None:
    if isinstance(exc, PrimaryGoalNotFound):
        raise HTTPException(
            status_code=404, detail="Primary wealth goal was not found"
        ) from exc
    if isinstance(exc, FamilyPlanNotFound):
        raise HTTPException(
            status_code=404, detail="Family wealth plan was not found"
        ) from exc
    if isinstance(exc, UnsafeProjection):
        raise HTTPException(
            status_code=409, detail="Family wealth projection could not be produced"
        ) from exc
    if isinstance(exc, (InvalidFamilyPlan, ValidationError)):
        raise _family_validation_error(exc) from exc
    raise exc


@router.post("/imports/preview", response_model=ImportPreview)
async def preview_import(workbook: UploadFile = File(...)) -> ImportPreview:
    if not workbook.filename or not workbook.filename.lower().endswith(".xlsx"):
        raise HTTPException(
            status_code=422, detail="Only .xlsx workbooks are supported"
        )
    payload = await workbook.read(MAX_WORKBOOK_BYTES + 1)
    if len(payload) > MAX_WORKBOOK_BYTES:
        raise HTTPException(status_code=413, detail="Workbook exceeds 20 MiB")
    if not payload:
        raise HTTPException(status_code=422, detail="Workbook is empty")
    try:
        return import_service.preview(payload, Path(workbook.filename).name)
    except Exception as exc:
        raise HTTPException(
            status_code=422, detail="Workbook could not be read"
        ) from exc


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
        raise HTTPException(
            status_code=404, detail="Import preview expired or was not found"
        ) from exc
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
        raise HTTPException(
            status_code=404, detail="No portfolio snapshot has been imported"
        )
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


@router.get("/annual-reviews", response_model=list[AnnualReviewResponse])
def annual_reviews(session: Session = Depends(get_session)) -> list[AnnualReviewResponse]:
    return list_annual_reviews(session)


@router.get("/annual-reviews/{year}", response_model=AnnualReviewResponse)
def annual_review(
    year: int = ApiPath(ge=2000, le=date.today().year),
    session: Session = Depends(get_session),
) -> AnnualReviewResponse:
    return get_annual_review(session, year)


@router.put("/annual-reviews/{year}", response_model=AnnualReviewResponse)
def replace_annual_review_overrides(
    payload: AnnualReviewOverrideUpdate,
    year: int = ApiPath(ge=2000, le=date.today().year),
    session: Session = Depends(get_session),
) -> AnnualReviewResponse:
    return save_annual_review_overrides(session, year, payload)


@router.delete("/annual-reviews/{year}", response_model=AnnualReviewResponse)
def remove_annual_review_overrides(
    year: int = ApiPath(ge=2000, le=date.today().year),
    session: Session = Depends(get_session),
) -> AnnualReviewResponse:
    return delete_annual_review_overrides(session, year)


@router.get("/goals/primary", response_model=PrimaryGoalResponse)
def primary_goal(session: Session = Depends(get_session)) -> PrimaryGoalResponse:
    try:
        return get_primary_goal_response(session)
    except PrimaryGoalNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidGoalConfiguration as exc:
        raise _goal_validation_error(exc) from exc


@router.put("/goals/primary", response_model=PrimaryGoalResponse)
def replace_primary_goal(
    payload: GoalConfigurationUpdate,
    session: Session = Depends(get_session),
) -> PrimaryGoalResponse:
    try:
        return update_primary_goal(session, payload)
    except PrimaryGoalNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidGoalConfiguration as exc:
        raise _goal_validation_error(exc) from exc


@router.get("/goals/family-plan", response_model=FamilyPlanResponse)
def family_plan(session: Session = Depends(get_session)) -> FamilyPlanResponse:
    try:
        return get_family_plan_response(session)
    except (
        FamilyPlanNotFound,
        PrimaryGoalNotFound,
        InvalidFamilyPlan,
        UnsafeProjection,
        ValidationError,
    ) as exc:
        _raise_family_plan_error(exc)


@router.put("/goals/family-plan", response_model=FamilyPlanResponse)
def replace_family_plan(
    payload: FamilyPlanUpdate,
    session: Session = Depends(get_session),
) -> FamilyPlanResponse:
    try:
        return save_family_plan(session, payload)
    except (
        FamilyPlanNotFound,
        PrimaryGoalNotFound,
        InvalidFamilyPlan,
        UnsafeProjection,
        ValidationError,
    ) as exc:
        _raise_family_plan_error(exc)


@router.post(
    "/goals/family-plan/restore-defaults", response_model=FamilyPlanResponse
)
def restore_default_family_plan(
    session: Session = Depends(get_session),
) -> FamilyPlanResponse:
    try:
        return restore_family_plan_defaults(session)
    except (
        FamilyPlanNotFound,
        PrimaryGoalNotFound,
        InvalidFamilyPlan,
        UnsafeProjection,
        ValidationError,
    ) as exc:
        _raise_family_plan_error(exc)
