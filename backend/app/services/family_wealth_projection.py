"""Pure monthly family wealth runway calculations.

This module deliberately accepts no persistence or schema objects.  Callers convert
their boundary types into the frozen value objects below.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext
from typing import Iterable


CENT = Decimal("0.01")
ZERO = Decimal("0")
ONE = Decimal("1")
TWELVE = Decimal("12")
HUNDRED = Decimal("100")
MAX_MONTHS = 600


class UnsafeProjection(ValueError):
    """Raised when inputs cannot produce a bounded, finite projection."""


@dataclass(frozen=True)
class ProjectionGoal:
    key: str
    name: str
    goal_type: str
    funding_treatment: str
    current_value_amount: Decimal
    target_date: date
    inflation_pct: Decimal
    priority: int
    enabled: bool = True


@dataclass(frozen=True)
class ProjectionInput:
    calculated_on: date
    end_date: date
    opening_financial: Decimal
    opening_property: Decimal
    monthly_contribution: Decimal
    contribution_step_up_enabled: bool
    contribution_step_up_pct: Decimal
    monthly_rent: Decimal
    rent_growth_pct: Decimal
    reinvest_rent_until: date
    property_growth_pct: Decimal
    withdrawal_rate_pct: Decimal
    amber_margin_pct: Decimal
    annual_financial_return_pct: Decimal
    goals: tuple[ProjectionGoal, ...] = ()
    birth_year: int = 1984
    birth_month: int = 7
    contribution_stop_age: int = 120
    milestone_date: date | None = None
    milestone_target_amount: Decimal | None = None


@dataclass(frozen=True)
class ProjectedGoalResult:
    goal_key: str
    goal_name: str
    goal_type: str
    funding_treatment: str
    target_date: date
    inflated_cost: Decimal
    available_before: Decimal
    funded_amount: Decimal
    shortfall: Decimal
    funded_pct: Decimal
    health_status: str
    health_reason: str


@dataclass(frozen=True)
class MonthlyRunwayPoint:
    on: date
    opening_financial: Decimal
    financial_growth: Decimal
    contribution: Decimal
    projected_monthly_rent: Decimal
    reinvested_rent: Decimal
    goal_outflows: Decimal
    closing_financial: Decimal
    opening_property: Decimal
    property_growth: Decimal
    closing_property: Decimal
    total_net_worth: Decimal
    events: tuple[ProjectedGoalResult, ...]


@dataclass(frozen=True)
class AnnualRunwayPoint:
    year: int
    on: date
    age: int
    financial_assets: Decimal
    property_value: Decimal
    total_net_worth: Decimal
    annual_contributions: Decimal
    annual_reinvested_rent: Decimal
    annual_rent_received: Decimal
    annual_financial_growth: Decimal
    annual_property_growth: Decimal
    annual_goal_outflows: Decimal
    events: tuple[ProjectedGoalResult, ...]


@dataclass(frozen=True)
class PassiveIncomeResult:
    goal_key: str
    target_date: date
    target_monthly_income: Decimal
    projected_monthly_rent: Decimal
    monthly_gap: Decimal
    annual_gap: Decimal
    required_corpus: Decimal
    supported_portfolio_monthly_income: Decimal
    total_supported_monthly_income: Decimal
    surplus_or_shortfall: Decimal
    on_track: bool
    later_goals_protected: bool
    earliest_sustainable_date: date | None


@dataclass(frozen=True)
class ProjectionResult:
    monthly_points: tuple[MonthlyRunwayPoint, ...]
    annual_points: tuple[AnnualRunwayPoint, ...]
    goal_results: tuple[ProjectedGoalResult, ...]
    passive_income: PassiveIncomeResult | None
    ending_financial: Decimal
    ending_property: Decimal
    ending_total: Decimal
    first_underfunded_goal_key: str | None
    milestone: MilestoneResult | None


@dataclass(frozen=True)
class MilestoneResult:
    target_date: date
    target_amount: Decimal
    projected_value: Decimal
    surplus_or_shortfall: Decimal
    on_track: bool


def as_decimal(value: Decimal | int | float | str, field: str = "value") -> Decimal:
    """Explicit, safe conversion helper for API/service boundaries."""
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise UnsafeProjection(f"{field} must be a finite decimal") from exc
    if not result.is_finite():
        raise UnsafeProjection(f"{field} must be finite")
    return result


def money(value: Decimal) -> Decimal:
    """Return a finite monetary result rounded to paise."""
    if not value.is_finite():
        raise UnsafeProjection("projection produced a non-finite monetary result")
    try:
        return value.quantize(CENT)
    except InvalidOperation as exc:
        raise UnsafeProjection("projection monetary result is too large") from exc


def _as_int(value: object, field: str) -> int:
    decimal_value = as_decimal(value, field)
    if decimal_value != decimal_value.to_integral_value():
        raise UnsafeProjection(f"{field} must be a whole number")
    try:
        return int(decimal_value)
    except (ValueError, OverflowError) as exc:
        raise UnsafeProjection(f"{field} must be a finite whole number") from exc


def _normalize(data: ProjectionInput) -> ProjectionInput:
    """Copy supported boundary numerics into canonical immutable Decimal values."""
    decimal_fields = (
        "opening_financial", "opening_property", "monthly_contribution",
        "contribution_step_up_pct", "monthly_rent", "rent_growth_pct",
        "property_growth_pct", "withdrawal_rate_pct", "amber_margin_pct",
        "annual_financial_return_pct",
    )
    normalized_values = {
        field: as_decimal(getattr(data, field), field) for field in decimal_fields
    }
    if data.milestone_target_amount is not None:
        normalized_values["milestone_target_amount"] = as_decimal(
            data.milestone_target_amount, "milestone_target_amount"
        )
    normalized_goals = tuple(
        replace(
            goal,
            current_value_amount=as_decimal(
                goal.current_value_amount, f"goal {goal.key} amount"
            ),
            inflation_pct=as_decimal(
                goal.inflation_pct, f"goal {goal.key} inflation_pct"
            ),
            priority=_as_int(goal.priority, f"goal {goal.key} priority"),
        )
        for goal in data.goals
    )
    return replace(data, **normalized_values, goals=normalized_goals)


def _month_index(value: date) -> int:
    return value.year * 12 + value.month - 1


def _month_end(index: int) -> date:
    year, zero_month = divmod(index, 12)
    month = zero_month + 1
    return date(year, month, monthrange(year, month)[1])


def _monthly_rate(annual_pct: Decimal, field: str) -> Decimal:
    annual_pct = as_decimal(annual_pct, field)
    base = ONE + annual_pct / HUNDRED
    if base <= ZERO:
        raise UnsafeProjection(f"{field} must imply a rate greater than -100%")
    try:
        with localcontext() as ctx:
            ctx.prec = 40
            rate = base ** (ONE / TWELVE) - ONE
    except (InvalidOperation, OverflowError) as exc:
        raise UnsafeProjection(f"{field} cannot be converted to a monthly rate") from exc
    if not rate.is_finite() or rate <= -ONE:
        raise UnsafeProjection(f"{field} has an unsafe monthly equivalent")
    return rate


def _validate(data: ProjectionInput) -> tuple[int, int]:
    start = _month_index(data.calculated_on)
    end = _month_index(data.end_date)
    if data.end_date < data.calculated_on or end < start:
        raise UnsafeProjection("end_date must be on or after calculated_on")
    months = end - start + 1
    if months > MAX_MONTHS:
        raise UnsafeProjection("projection horizon cannot exceed 600 months")
    if data.opening_financial < ZERO or data.opening_property < ZERO:
        raise UnsafeProjection("opening balances cannot be negative")
    if data.monthly_contribution < ZERO or data.monthly_rent < ZERO:
        raise UnsafeProjection("monthly inflows cannot be negative")
    if data.withdrawal_rate_pct <= ZERO:
        raise UnsafeProjection("withdrawal_rate_pct must be positive")
    _monthly_rate(data.annual_financial_return_pct, "annual_financial_return_pct")
    _monthly_rate(data.property_growth_pct, "property_growth_pct")
    _monthly_rate(data.rent_growth_pct, "rent_growth_pct")
    _monthly_rate(data.contribution_step_up_pct, "contribution_step_up_pct")
    keys = [goal.key for goal in data.goals]
    if len(keys) != len(set(keys)):
        raise UnsafeProjection("goal keys must be unique")
    for goal in data.goals:
        amount = goal.current_value_amount
        if amount < ZERO:
            raise UnsafeProjection(f"goal {goal.key} amount cannot be negative")
        expected_treatment = {
            "house": "asset_conversion",
            "passive_income": "income_target",
            "education": "expense",
            "marriage": "expense",
        }.get(goal.goal_type)
        if expected_treatment is None:
            raise UnsafeProjection(f"goal {goal.key} has an unknown goal_type")
        if goal.funding_treatment != expected_treatment:
            raise UnsafeProjection(
                f"goal {goal.key} requires {expected_treatment} funding treatment"
            )
        _monthly_rate(goal.inflation_pct, f"goal {goal.key} inflation_pct")
        if goal.enabled and goal.target_date < data.calculated_on:
            raise UnsafeProjection(f"goal {goal.key} target_date precedes calculated_on")
        if goal.enabled and _month_index(goal.target_date) > end:
            raise UnsafeProjection(f"goal {goal.key} falls outside projection horizon")
    enabled_income_targets = sum(
        goal.enabled and goal.funding_treatment == "income_target"
        for goal in data.goals
    )
    if enabled_income_targets > 1:
        raise UnsafeProjection("only one enabled income target is supported")
    return start, end


def _inflated_cost(goal: ProjectionGoal, calculated_on: date) -> Decimal:
    months = _month_index(goal.target_date) - _month_index(calculated_on)
    rate = _monthly_rate(goal.inflation_pct, f"goal {goal.key} inflation_pct")
    with localcontext() as ctx:
        ctx.prec = 40
        return money(goal.current_value_amount * ((ONE + rate) ** months))


def _annual_points(
    points: Iterable[MonthlyRunwayPoint], birth_year: int, birth_month: int
) -> tuple[AnnualRunwayPoint, ...]:
    grouped: dict[int, list[MonthlyRunwayPoint]] = {}
    for point in points:
        grouped.setdefault(point.on.year, []).append(point)
    result = []
    for year, items in grouped.items():
        last = items[-1]
        events = tuple(event for item in items for event in item.events)
        result.append(AnnualRunwayPoint(
            year=year, on=last.on,
            age=last.on.year - birth_year - (last.on.month < birth_month),
            financial_assets=last.closing_financial,
            property_value=last.closing_property, total_net_worth=last.total_net_worth,
            annual_contributions=money(sum((p.contribution for p in items), ZERO)),
            annual_reinvested_rent=money(sum((p.reinvested_rent for p in items), ZERO)),
            annual_rent_received=money(sum((p.projected_monthly_rent for p in items), ZERO)),
            annual_financial_growth=money(sum((p.financial_growth for p in items), ZERO)),
            annual_property_growth=money(sum((p.property_growth for p in items), ZERO)),
            annual_goal_outflows=money(sum((p.goal_outflows for p in items), ZERO)),
            events=events,
        ))
    return tuple(result)


def project_family_wealth(data: ProjectionInput) -> ProjectionResult:
    """Calculate one scenario using full month buckets ending at month-end.

    The bucket containing ``calculated_on`` is a full bucket, even for a partial
    calendar month. Rent follows calendar years and steps every January.
    Contributions step in January only once at least twelve full plan buckets have
    elapsed, so a mid-year plan intentionally waits until the following January.
    """
    data = _normalize(data)
    start, end = _validate(data)
    financial_rate = _monthly_rate(data.annual_financial_return_pct, "annual_financial_return_pct")
    property_rate = _monthly_rate(data.property_growth_pct, "property_growth_pct")
    step_factor = ONE + data.contribution_step_up_pct / HUNDRED
    rent_factor = ONE + data.rent_growth_pct / HUNDRED
    goals = tuple(g for g in data.goals if g.enabled)
    event_goals = tuple(g for g in goals if g.funding_treatment != "income_target")
    passive_goals = tuple(g for g in goals if g.funding_treatment == "income_target")
    inflated = {g.key: _inflated_cost(g, data.calculated_on) for g in goals}

    financial = money(data.opening_financial)
    property_value = money(data.opening_property)
    contribution = data.monthly_contribution
    rent = data.monthly_rent
    points: list[MonthlyRunwayPoint] = []
    goal_results: list[ProjectedGoalResult] = []
    first_underfunded: str | None = None

    for index in range(start, end + 1):
        on = _month_end(index)
        age = on.year - data.birth_year - (on.month < data.birth_month)
        # Rent is a calendar-year assumption; every January receives its step.
        if on.month == 1 and on.year > data.calculated_on.year:
            if (
                data.contribution_step_up_enabled
                # Contribution escalation instead follows completed plan buckets.
                and index - start >= 12
            ):
                contribution *= step_factor
            rent *= rent_factor
        opening_financial = financial
        opening_property = property_value
        financial_growth = money(opening_financial * financial_rate)
        property_growth = money(opening_property * property_rate)
        financial = money(opening_financial + financial_growth)
        property_value = money(opening_property + property_growth)
        contribution_out = money(contribution if age < data.contribution_stop_age else ZERO)
        financial = money(financial + contribution_out)
        projected_rent = money(rent)
        reinvested = (
            projected_rent
            if index <= _month_index(data.reinvest_rent_until)
            else money(ZERO)
        )
        financial = money(financial + reinvested)

        month_events: list[ProjectedGoalResult] = []
        goal_outflows = ZERO
        due = sorted(
            (g for g in event_goals if _month_index(g.target_date) == index),
            key=lambda g: (g.priority, g.key),
        )
        for goal in due:
            cost = inflated[goal.key]
            available = financial
            funded = money(min(available, cost))
            shortfall = money(cost - funded)
            financial = money(financial - funded)
            if goal.funding_treatment == "asset_conversion":
                property_value = money(property_value + funded)
            goal_outflows += funded
            funded_pct = money((funded / cost * HUNDRED) if cost else HUNDRED)
            if shortfall > ZERO:
                health_status = "red"
                health_reason = "Goal is underfunded in this scenario"
            else:
                margin_pct = (
                    (available - cost) / cost * HUNDRED if cost else HUNDRED
                )
                if margin_pct >= data.amber_margin_pct:
                    health_status = "green"
                    health_reason = "Funded with the configured safety margin"
                else:
                    health_status = "amber"
                    health_reason = "Funded with less than the configured safety margin"
            event = ProjectedGoalResult(
                goal_key=goal.key, goal_name=goal.name, goal_type=goal.goal_type,
                funding_treatment=goal.funding_treatment, target_date=goal.target_date,
                inflated_cost=cost, available_before=available, funded_amount=funded,
                shortfall=shortfall, funded_pct=funded_pct,
                health_status=health_status, health_reason=health_reason,
            )
            month_events.append(event)
            goal_results.append(event)
            if shortfall > ZERO and first_underfunded is None:
                first_underfunded = goal.key

        points.append(MonthlyRunwayPoint(
            on=on, opening_financial=opening_financial,
            financial_growth=financial_growth, contribution=contribution_out,
            projected_monthly_rent=projected_rent, reinvested_rent=reinvested,
            goal_outflows=money(goal_outflows), closing_financial=financial,
            opening_property=opening_property, property_growth=property_growth,
            closing_property=property_value,
            total_net_worth=money(financial + property_value), events=tuple(month_events),
        ))

    passive = _passive_result(passive_goals, points, goal_results, inflated, data)
    milestone = None
    if data.milestone_date is not None and data.milestone_target_amount is not None:
        milestone_point = next(
            (p for p in points if _month_index(p.on) == _month_index(data.milestone_date)),
            None,
        )
        if milestone_point is None:
            raise UnsafeProjection("milestone falls outside projection horizon")
        projected = milestone_point.total_net_worth
        milestone = MilestoneResult(
            target_date=data.milestone_date,
            target_amount=data.milestone_target_amount,
            projected_value=projected,
            surplus_or_shortfall=money(projected - data.milestone_target_amount),
            on_track=projected >= data.milestone_target_amount,
        )
    return ProjectionResult(
        monthly_points=tuple(points), annual_points=_annual_points(
            points, data.birth_year, data.birth_month
        ),
        goal_results=tuple(goal_results), passive_income=passive,
        ending_financial=financial, ending_property=property_value,
        ending_total=money(financial + property_value),
        first_underfunded_goal_key=first_underfunded,
        milestone=milestone,
    )


def _passive_result(
    passive_goals: tuple[ProjectionGoal, ...],
    points: list[MonthlyRunwayPoint],
    goal_results: list[ProjectedGoalResult],
    inflated: dict[str, Decimal],
    data: ProjectionInput,
) -> PassiveIncomeResult | None:
    if not passive_goals:
        return None
    goal = sorted(passive_goals, key=lambda g: (g.priority, g.key))[0]
    target_index = _month_index(goal.target_date)
    target_point = next((p for p in points if _month_index(p.on) == target_index), None)
    if target_point is None:
        raise UnsafeProjection(f"passive income goal {goal.key} falls outside projection horizon")
    later = [g for g in data.goals if g.enabled and g.funding_treatment != "income_target" and g.target_date > goal.target_date]
    result_by_key = {r.goal_key: r for r in goal_results}
    target = inflated[goal.key]
    rent = target_point.projected_monthly_rent
    gap = money(max(ZERO, target - rent))
    annual_gap = money(gap * TWELVE)
    required = money(annual_gap / (data.withdrawal_rate_pct / HUNDRED))
    supported_portfolio = money(target_point.closing_financial * data.withdrawal_rate_pct / HUNDRED / TWELVE)
    total_supported = money(supported_portfolio + rent)
    later_funded = all(
        g.key in result_by_key and result_by_key[g.key].shortfall == ZERO
        for g in later
    )
    later_reserve_preserved = later_funded and all(
        result_by_key[g.key].available_before
        - result_by_key[g.key].funded_amount
        + CENT
        >= required
        for g in later
    )

    def sustainable_from(candidate: MonthlyRunwayPoint) -> bool:
        if not later_funded:
            return False
        for point in points:
            if point.on < candidate.on:
                continue
            point_gap = money(max(ZERO, target - point.projected_monthly_rent))
            point_required = money(
                point_gap * TWELVE / (data.withdrawal_rate_pct / HUNDRED)
            )
            if point.closing_financial < point_required:
                return False
        return True

    later_protected = later_reserve_preserved
    corpus_met = target_point.closing_financial >= required
    earliest = next(
        (
            point.on
            for point in points
            if point.on >= target_point.on and sustainable_from(point)
        ),
        None,
    )
    return PassiveIncomeResult(
        goal_key=goal.key, target_date=goal.target_date,
        target_monthly_income=target, projected_monthly_rent=rent,
        monthly_gap=gap, annual_gap=annual_gap, required_corpus=required,
        supported_portfolio_monthly_income=supported_portfolio,
        total_supported_monthly_income=total_supported,
        surplus_or_shortfall=money(target_point.closing_financial - required),
        on_track=corpus_met and later_protected,
        later_goals_protected=later_protected, earliest_sustainable_date=earliest,
    )
