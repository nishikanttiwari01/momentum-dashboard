"""Pure calculations for projecting a wealth goal."""

from dataclasses import dataclass
from datetime import date
import calendar
import math
from numbers import Integral, Real

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.repos.models import WealthGoal, WealthGoalScenario
from app.schemas.wealth_portfolio import (
    GoalConfigurationUpdate,
    GoalScenarioProjection,
    GoalScenarioSettings,
    GoalSettings,
    GoalTrajectoryPoint,
    PrimaryGoalResponse,
)
from app.services.wealth_summary_service import build_summary


@dataclass(frozen=True)
class TrajectoryPoint:
    on: date
    balance: float


def _finite_number(value: Real, name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, Real)
        or not math.isfinite(value)
    ):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def _positive_months(months: int) -> int:
    if isinstance(months, bool) or not isinstance(months, Integral) or months <= 0:
        raise ValueError("months must be a positive integer")
    return int(months)


def _projection_inputs(
    start: Real, annual_return_pct: Real, monthly: Real
) -> tuple[float, float, float]:
    start = _finite_number(start, "start")
    annual_return_pct = _finite_number(annual_return_pct, "annual_return_pct")
    monthly = _finite_number(monthly, "monthly")
    if monthly < 0:
        raise ValueError("monthly must not be negative")
    if annual_return_pct <= -1200:
        raise ValueError("annual return must imply a monthly rate above -100%")
    return start, annual_return_pct, monthly


def project_balance(
    start: Real, annual_return_pct: Real, monthly: Real, months: int
) -> float:
    """Project a balance using contributions made at each month's end."""
    start, annual_return_pct, monthly = _projection_inputs(
        start, annual_return_pct, monthly
    )
    months = _positive_months(months)
    rate = annual_return_pct / 1200
    try:
        if rate == 0:
            result = start + monthly * months
        else:
            log_growth = months * math.log1p(rate)
            growth = math.exp(log_growth)
            annuity_factor = math.expm1(log_growth) / rate
            result = start * growth + monthly * annuity_factor
    except OverflowError as exc:
        raise ValueError(
            "projection must produce a finite projection balance"
        ) from exc
    if not math.isfinite(result):
        raise ValueError("projection must produce a finite projection balance")
    return result


def required_monthly_contribution(
    start: Real, target: Real, months: int, annual_return_pct: Real
) -> float:
    """Return the non-negative monthly amount needed to reach ``target``."""
    start = _finite_number(start, "start")
    target = _finite_number(target, "target")
    annual_return_pct = _finite_number(annual_return_pct, "annual_return_pct")
    months = _positive_months(months)
    if annual_return_pct <= -1200:
        raise ValueError("annual return must imply a monthly rate above -100%")

    rate = annual_return_pct / 1200
    if rate == 0:
        return max(0.0, (target - start) / months)
    log_growth = months * math.log1p(rate)
    growth = math.exp(log_growth)
    shortfall = target - start * growth
    if shortfall <= 0:
        return 0.0
    annuity_factor = math.expm1(log_growth) / rate
    return max(0.0, shortfall / annuity_factor)


def whole_months_between(calculated_on: date, deadline: date) -> int:
    """Count complete calendar months from calculation date to deadline."""
    if not isinstance(calculated_on, date) or not isinstance(deadline, date):
        raise ValueError("calculated_on and deadline must be dates")
    if deadline < calculated_on:
        raise ValueError("deadline must not precede calculated_on")
    months = (deadline.year - calculated_on.year) * 12
    months += deadline.month - calculated_on.month
    if deadline.day < calculated_on.day:
        months -= 1
    return months


def _month_end_after(value: date, offset: int) -> date:
    month_index = value.year * 12 + value.month - 1 + offset
    year, zero_based_month = divmod(month_index, 12)
    month = zero_based_month + 1
    return date(year, month, calendar.monthrange(year, month)[1])


def monthly_trajectory(
    calculated_on: date,
    start: Real,
    annual_return_pct: Real,
    monthly: Real,
    months: int,
) -> tuple[TrajectoryPoint, ...]:
    """Build future month-end balances for a fixed number of months."""
    if not isinstance(calculated_on, date):
        raise ValueError("calculated_on must be a date")
    start, annual_return_pct, monthly = _projection_inputs(
        start, annual_return_pct, monthly
    )
    months = _positive_months(months)
    return tuple(
        TrajectoryPoint(
            on=_month_end_after(calculated_on, month),
            balance=project_balance(start, annual_return_pct, monthly, month),
        )
        for month in range(1, months + 1)
    )


def projected_completion_date(
    calculated_on: date,
    start: Real,
    target: Real,
    annual_return_pct: Real,
    monthly: Real,
) -> date | None:
    """Find the first reaching month-end, capped at 600 projected months."""
    if not isinstance(calculated_on, date):
        raise ValueError("calculated_on must be a date")
    start, annual_return_pct, monthly = _projection_inputs(
        start, annual_return_pct, monthly
    )
    target = _finite_number(target, "target")
    if start >= target:
        return calculated_on
    for point in monthly_trajectory(
        calculated_on, start, annual_return_pct, monthly, 600
    ):
        if point.balance >= target:
            return point.on
    return None


class PrimaryGoalNotFound(LookupError):
    pass


@dataclass(frozen=True)
class GoalValidationIssue:
    loc: tuple[str | int, ...]
    message: str
    error_type: str = "value_error"


class InvalidGoalConfiguration(ValueError):
    def __init__(self, issue: GoalValidationIssue):
        super().__init__(issue.message)
        self.issue = issue


def _invalid(loc: tuple[str | int, ...], message: str) -> InvalidGoalConfiguration:
    return InvalidGoalConfiguration(GoalValidationIssue(loc=loc, message=message))


def _primary_goal(session: Session) -> WealthGoal:
    goal = session.scalar(
        select(WealthGoal)
        .where(WealthGoal.is_primary.is_(True))
        .order_by(WealthGoal.id)
        .limit(1)
    )
    if goal is None:
        raise PrimaryGoalNotFound("Primary wealth goal seed is missing")
    return goal


def _trajectory(points: tuple[TrajectoryPoint, ...]) -> list[GoalTrajectoryPoint]:
    return [
        GoalTrajectoryPoint(on=point.on, balance_inr=point.balance) for point in points
    ]


def get_primary_goal_response(
    session: Session, today: date | None = None
) -> PrimaryGoalResponse:
    calculated_on = today or date.today()
    goal = _primary_goal(session)
    scenarios = list(
        session.scalars(
            select(WealthGoalScenario)
            .where(WealthGoalScenario.goal_id == goal.id)
            .order_by(WealthGoalScenario.display_order, WealthGoalScenario.id)
        )
    )
    if [row.scenario_key for row in scenarios] != [
        "conservative",
        "expected",
        "optimistic",
    ]:
        raise _invalid(
            ("scenarios",), "Primary goal must have exactly three ordered scenarios"
        )

    settings = GoalSettings(
        name=goal.name,
        target_amount_inr=goal.target_amount_inr,
        deadline=goal.deadline,
    )
    scenario_settings = [
        GoalScenarioSettings(
            scenario_key=row.scenario_key,
            annual_return_pct=row.annual_return_pct,
            monthly_contribution_inr=row.monthly_contribution_inr,
        )
        for row in scenarios
    ]
    summary = build_summary(session)
    if summary.net_worth_market_value_inr is None:
        return PrimaryGoalResponse(
            goal=settings,
            scenario_projections=[
                GoalScenarioProjection(settings=item) for item in scenario_settings
            ],
            calculated_on=calculated_on,
            data_health=summary.data_health,
        )

    months = whole_months_between(calculated_on, goal.deadline)
    if months <= 0:
        raise _invalid(
            ("goal", "deadline"),
            "Goal deadline must include a future monthly period",
        )
    if months > 600:
        raise _invalid(
            ("goal", "deadline"),
            "Goal deadline cannot exceed 600 monthly periods",
        )
    current = summary.net_worth_market_value_inr
    expected = scenario_settings[1]
    required = required_monthly_contribution(
        current, goal.target_amount_inr, months, expected.annual_return_pct
    )
    required_points = monthly_trajectory(
        calculated_on, current, expected.annual_return_pct, required, months
    )
    projections = []
    for item in scenario_settings:
        projected = project_balance(
            current, item.annual_return_pct, item.monthly_contribution_inr, months
        )
        projections.append(
            GoalScenarioProjection(
                settings=item,
                projected_deadline_value_inr=projected,
                surplus_or_shortfall_inr=projected - goal.target_amount_inr,
                on_track=projected >= goal.target_amount_inr,
                projected_completion_date=projected_completion_date(
                    calculated_on,
                    current,
                    goal.target_amount_inr,
                    item.annual_return_pct,
                    item.monthly_contribution_inr,
                ),
                trajectory=_trajectory(
                    monthly_trajectory(
                        calculated_on,
                        current,
                        item.annual_return_pct,
                        item.monthly_contribution_inr,
                        months,
                    )
                ),
            )
        )
    return PrimaryGoalResponse(
        goal=settings,
        scenario_projections=projections,
        calculated_on=calculated_on,
        snapshot_id=summary.snapshot_id,
        current_value_inr=current,
        achieved_pct=current * 100 / goal.target_amount_inr,
        remaining_inr=max(0, goal.target_amount_inr - current),
        required_monthly_contribution_inr=required,
        required_trajectory=_trajectory(required_points),
        data_health=summary.data_health,
    )


def update_primary_goal(
    session: Session,
    payload: GoalConfigurationUpdate,
    today: date | None = None,
) -> PrimaryGoalResponse:
    calculated_on = today or date.today()
    if payload.goal.deadline <= calculated_on:
        raise _invalid(
            ("goal", "deadline"),
            "Goal deadline must be after the calculation date",
        )
    months = whole_months_between(calculated_on, payload.goal.deadline)
    if months <= 0:
        raise _invalid(
            ("goal", "deadline"),
            "Goal deadline must include a future monthly period",
        )
    if months > 600:
        raise _invalid(
            ("goal", "deadline"),
            "Goal deadline cannot exceed 600 monthly periods",
        )

    try:
        goal = _primary_goal(session)
        goal.name = payload.goal.name
        goal.target_amount_inr = payload.goal.target_amount_inr
        goal.deadline = payload.goal.deadline
        session.query(WealthGoalScenario).filter(
            WealthGoalScenario.goal_id == goal.id
        ).delete(synchronize_session=False)
        for order, item in enumerate(payload.scenarios):
            session.add(
                WealthGoalScenario(
                    id=f"{goal.id[:-3]}{order + 200:03d}",
                    goal_id=goal.id,
                    scenario_key=item.scenario_key,
                    annual_return_pct=item.annual_return_pct,
                    monthly_contribution_inr=item.monthly_contribution_inr,
                    display_order=order,
                )
            )
        session.flush()
        response = get_primary_goal_response(session, today=calculated_on)
        session.commit()
        return response
    except Exception:
        session.rollback()
        raise
