"""Persistence orchestration for the family wealth runway."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
import uuid

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from app.repos.models import (
    FamilyWealthGoal, FamilyWealthPlan, PortfolioAsset,
    PortfolioFxRate, PortfolioSnapshot, WealthGoal, WealthGoalScenario,
)
from app.schemas.wealth_portfolio import (
    AnnualRunwayEvent, AnnualRunwayPoint, FamilyPlanAssumptions,
    FamilyPlanResponse, FamilyPlanUpdate, FamilyScenarioProjection,
    FamilyScenarioSettings, GoalHealth, LinkedGoalSettings,
    PassiveIncomeAnalysis, WealthSummary,
)
from app.services.family_wealth_projection import (
    ProjectionGoal, ProjectionInput, UnsafeProjection, project_family_wealth,
)
from app.services.wealth_fx_service import FxResult, FxUnavailable, get_usd_inr
from app.services.wealth_goal_service import (
    PrimaryGoalNotFound, get_primary_goal_response,
)


SCENARIO_KEYS = ("conservative", "expected", "optimistic")
GOAL_NAMESPACE = uuid.UUID("f7bbbf68-47e5-4cd6-8987-d0b3e3898f11")
FINANCIAL_TYPES = {
    "mutual_fund", "mutual_funds", "stock", "stocks", "etf", "etfs",
    "debt", "cash", "us_holding", "us_holdings",
}
PROPERTY_TYPES = {"property", "land", "real_estate"}


class FamilyPlanNotFound(LookupError):
    pass


class InvalidFamilyPlan(ValueError):
    pass


def _decimal(value: float) -> Decimal:
    return Decimal(str(value))


def _plan(session: Session) -> FamilyWealthPlan:
    rows = list(session.scalars(select(FamilyWealthPlan).order_by(FamilyWealthPlan.id)))
    if len(rows) != 1:
        raise FamilyPlanNotFound("Family wealth plan singleton is missing or invalid")
    return rows[0]


def _primary_rows(session: Session):
    goal = session.scalar(select(WealthGoal).where(WealthGoal.is_primary.is_(True)).order_by(WealthGoal.id).limit(1))
    if goal is None:
        raise PrimaryGoalNotFound("Primary wealth goal seed is missing")
    scenarios = list(session.scalars(select(WealthGoalScenario).where(WealthGoalScenario.goal_id == goal.id).order_by(WealthGoalScenario.display_order, WealthGoalScenario.id)))
    if tuple(row.scenario_key for row in scenarios) != SCENARIO_KEYS:
        raise InvalidFamilyPlan("Primary goal must have exactly three ordered scenarios")
    return goal, scenarios


def _settings(plan, rows):
    assumptions = FamilyPlanAssumptions(
        monthly_contribution_inr=plan.monthly_contribution_inr,
        contribution_step_up_enabled=plan.contribution_step_up_enabled,
        contribution_step_up_pct=plan.contribution_step_up_pct,
        monthly_rent_inr=plan.monthly_rent_inr, rent_growth_pct=plan.rent_growth_pct,
        reinvest_rent_until=plan.reinvest_rent_until,
        property_growth_pct=plan.property_growth_pct,
        withdrawal_rate_pct=plan.withdrawal_rate_pct,
        amber_margin_pct=plan.amber_margin_pct,
    )
    goals = [LinkedGoalSettings(
        goal_key=row.goal_key, name=row.name, goal_type=row.goal_type,
        current_value_amount_inr=row.current_value_amount_inr,
        target_date=row.target_date, inflation_pct=row.inflation_pct,
        funding_treatment=row.funding_treatment, priority=row.priority,
        enabled=row.enabled, display_order=row.display_order,
    ) for row in rows]
    return assumptions, goals


def _latest_snapshot_needs_usd(session: Session) -> bool:
    snapshot = session.scalar(select(PortfolioSnapshot).order_by(
        PortfolioSnapshot.as_of.desc(), PortfolioSnapshot.created_at.desc(),
        PortfolioSnapshot.id.desc(),
    ).limit(1))
    if snapshot is None:
        return False
    assets = session.scalars(select(PortfolioAsset).where(
        PortfolioAsset.snapshot_id == snapshot.id,
        PortfolioAsset.market_value.is_not(None),
    ))
    return any(
        asset.currency.upper() == "USD"
        and asset.asset_type.lower() in FINANCIAL_TYPES | PROPERTY_TYPES
        for asset in assets
    )


def _matching_fx(session: Session, effective_on: date) -> PortfolioFxRate | None:
    for row in session.new:
        if (
            isinstance(row, PortfolioFxRate)
            and row.base_currency == "USD"
            and row.quote_currency == "INR"
            and row.effective_on == effective_on
        ):
            return row
    return session.scalar(select(PortfolioFxRate).where(
        PortfolioFxRate.base_currency == "USD",
        PortfolioFxRate.quote_currency == "INR",
        PortfolioFxRate.effective_on == effective_on,
    ).limit(1))


def _resolve_connection_bound_fx(session: Session, calculated_on: date) -> FxResult | None:
    staged = max(
        (
            row for row in session.new
            if isinstance(row, PortfolioFxRate)
            and row.base_currency == "USD"
            and row.quote_currency == "INR"
            and row.effective_on <= calculated_on
        ),
        key=lambda row: row.effective_on,
        default=None,
    )
    if staged is not None:
        return FxResult(
            staged.rate, staged.effective_on, staged.source, staged.fetched_at,
            staged.effective_on != calculated_on,
        )
    try:
        fx = get_usd_inr(session, calculated_on, persist=False)
    except FxUnavailable:
        return None
    if not fx.is_fallback and _matching_fx(session, fx.effective_on) is None:
        session.add(PortfolioFxRate(
            base_currency="USD", quote_currency="INR",
            effective_on=fx.effective_on, rate=fx.rate,
            source=fx.source, fetched_at=fx.fetched_at,
        ))
    return fx


def _resolve_opening_fx(session: Session, calculated_on: date) -> FxResult | None:
    """Resolve portfolio FX without committing or rolling back the caller."""
    caller_bind = session.get_bind()
    if isinstance(caller_bind, Connection) and caller_bind.in_transaction():
        if not _latest_snapshot_needs_usd(session):
            return None
        return _resolve_connection_bound_fx(session, calculated_on)

    cache_bind = caller_bind.engine if isinstance(caller_bind, Connection) else caller_bind
    with Session(bind=cache_bind) as cache_session:
        if not _latest_snapshot_needs_usd(cache_session):
            return None
        try:
            return get_usd_inr(cache_session, calculated_on)
        except FxUnavailable:
            return None


def _opening_balances(session: Session, calculated_on: date, fx: FxResult | None):
    snapshot = session.scalar(select(PortfolioSnapshot).order_by(
        PortfolioSnapshot.as_of.desc(), PortfolioSnapshot.created_at.desc(),
        PortfolioSnapshot.id.desc(),
    ).limit(1))
    if snapshot is None:
        return None, Decimal("0"), Decimal("0"), "empty"
    assets = list(session.scalars(select(PortfolioAsset).where(PortfolioAsset.snapshot_id == snapshot.id)))
    recognized = [asset for asset in assets if asset.asset_type.lower() in FINANCIAL_TYPES | PROPERTY_TYPES]
    needs_usd = any(asset.currency.upper() == "USD" and asset.market_value is not None for asset in recognized)
    financial = Decimal("0")
    property_value = Decimal("0")
    warning = needs_usd and (fx is None or fx.effective_on != calculated_on)
    for asset in recognized:
        kind = asset.asset_type.lower()
        if kind not in FINANCIAL_TYPES | PROPERTY_TYPES:
            continue
        amount = asset.market_value
        if amount is None:
            continue
        value = _decimal(amount)
        currency = asset.currency.upper()
        if currency == "USD":
            if fx is None:
                warning = True
                continue
            value *= _decimal(fx.rate)
        elif currency != "INR":
            warning = True
            continue
        if kind in PROPERTY_TYPES:
            property_value += value
        else:
            financial += value
    return snapshot, financial, property_value, "warning" if warning else "fresh"


def _projection(settings, goals, result):
    by_key = {goal.goal_key: goal for goal in goals}
    event = lambda item: AnnualRunwayEvent(
        goal_key=item.goal_key, goal_name=item.goal_name, goal_type=item.goal_type,
        funding_treatment=item.funding_treatment, amount_inr=float(item.inflated_cost),
        funded_amount_inr=float(item.funded_amount), shortfall_inr=float(item.shortfall),
    )
    points = [AnnualRunwayPoint(
        on=item.on, financial_assets_inr=float(item.financial_assets),
        property_value_inr=float(item.property_value), total_net_worth_inr=float(item.total_net_worth),
        annual_contributions_inr=float(item.annual_contributions),
        annual_rent_inr=float(item.annual_reinvested_rent),
        financial_growth_inr=float(item.annual_financial_growth),
        property_growth_inr=float(item.annual_property_growth),
        goal_outflows_inr=float(item.annual_goal_outflows), events=[event(x) for x in item.events],
    ) for item in result.annual_points]
    health = [GoalHealth(
        goal=by_key[item.goal_key], inflated_cost_inr=float(item.inflated_cost),
        available_before_inr=float(item.available_before), funded_amount_inr=float(item.funded_amount),
        shortfall_inr=float(item.shortfall), funded_pct=float(item.funded_pct),
        status=item.health_status, reason=item.health_reason,
    ) for item in result.goal_results]
    passive = None
    if result.passive_income:
        item = result.passive_income
        passive = PassiveIncomeAnalysis(
            target_date=item.target_date, target_monthly_income_inr=float(item.target_monthly_income),
            projected_monthly_rent_inr=float(item.projected_monthly_rent), portfolio_monthly_gap_inr=float(item.monthly_gap),
            required_corpus_inr=float(item.required_corpus), supported_portfolio_monthly_income_inr=float(item.supported_portfolio_monthly_income),
            total_monthly_income_inr=float(item.total_supported_monthly_income), surplus_or_shortfall_inr=float(item.surplus_or_shortfall),
            on_track=item.on_track, later_goals_protected=item.later_goals_protected,
            earliest_sustainable_date=item.earliest_sustainable_date,
        )
    return FamilyScenarioProjection(
        settings=settings, annual_points=points, goal_health=health, passive_income=passive,
        ending_financial_assets_inr=float(result.ending_financial), ending_property_value_inr=float(result.ending_property),
        ending_total_net_worth_inr=float(result.ending_total), first_underfunded_goal_key=result.first_underfunded_goal_key,
    )


def _family_plan_response(session: Session, calculated_on: date, fx: FxResult | None) -> FamilyPlanResponse:
    plan = _plan(session)
    goal_rows = list(session.scalars(select(FamilyWealthGoal).where(FamilyWealthGoal.plan_id == plan.id).order_by(FamilyWealthGoal.display_order, FamilyWealthGoal.goal_key)))
    _, scenario_rows = _primary_rows(session)
    assumptions, goals = _settings(plan, goal_rows)
    snapshot, opening_financial, opening_property, health = _opening_balances(session, calculated_on, fx)
    summary = WealthSummary(
        snapshot_id=snapshot.id if snapshot else None,
        as_of=snapshot.as_of if snapshot else None,
        net_worth_market_value_inr=(float(opening_financial + opening_property) if snapshot else None),
        invested_capital_inr=(float(opening_financial + opening_property) if snapshot else None),
        data_health=health,
    )
    primary = get_primary_goal_response(session, today=calculated_on, summary=summary)
    enabled = [goal for goal in goals if goal.enabled]
    end_date = max((goal.target_date for goal in enabled), default=calculated_on)
    projection_goals = tuple(ProjectionGoal(
        key=g.goal_key, name=g.name, goal_type=g.goal_type,
        funding_treatment=g.funding_treatment, current_value_amount=_decimal(g.current_value_amount_inr),
        target_date=g.target_date, inflation_pct=_decimal(g.inflation_pct), priority=g.priority, enabled=g.enabled,
    ) for g in goals)
    projections = []
    try:
        for row in scenario_rows:
            scenario = FamilyScenarioSettings(scenario_key=row.scenario_key, annual_return_pct=row.annual_return_pct)
            result = project_family_wealth(ProjectionInput(
                calculated_on=calculated_on, end_date=end_date,
                opening_financial=opening_financial, opening_property=opening_property,
                monthly_contribution=_decimal(assumptions.monthly_contribution_inr),
                contribution_step_up_enabled=assumptions.contribution_step_up_enabled,
                contribution_step_up_pct=_decimal(assumptions.contribution_step_up_pct), monthly_rent=_decimal(assumptions.monthly_rent_inr),
                rent_growth_pct=_decimal(assumptions.rent_growth_pct), reinvest_rent_until=assumptions.reinvest_rent_until,
                property_growth_pct=_decimal(assumptions.property_growth_pct), withdrawal_rate_pct=_decimal(assumptions.withdrawal_rate_pct),
                amber_margin_pct=_decimal(assumptions.amber_margin_pct), annual_financial_return_pct=_decimal(row.annual_return_pct), goals=projection_goals,
            ))
            projections.append(_projection(scenario, goals, result))
        return FamilyPlanResponse(primary_goal=primary, calculated_on=calculated_on, snapshot_id=snapshot.id if snapshot else None,
            data_health=health, assumptions=assumptions, goals=goals, scenario_projections=projections)
    except UnsafeProjection:
        raise
    except ValidationError as exc:
        raise InvalidFamilyPlan(f"Family wealth projection is invalid: {exc}") from exc


def get_family_plan_response(session: Session, today: date | None = None) -> FamilyPlanResponse:
    calculated_on = today or date.today()
    fx = _resolve_opening_fx(session, calculated_on)
    return _family_plan_response(session, calculated_on, fx)


def _apply(session, plan, payload, *, base_age: int | None = None):
    if base_age is not None:
        plan.base_age = base_age
    for field, value in payload.assumptions.model_dump().items():
        setattr(plan, field, value)
    existing = {row.goal_key: row for row in session.scalars(select(FamilyWealthGoal).where(FamilyWealthGoal.plan_id == plan.id))}
    keep = {goal.goal_key for goal in payload.goals}
    for key, row in existing.items():
        if key not in keep:
            session.delete(row)
    for goal in payload.goals:
        row = existing.get(goal.goal_key)
        if row is None:
            row = FamilyWealthGoal(id=str(uuid.uuid5(GOAL_NAMESPACE, f"{plan.id}:{goal.goal_key}")), plan_id=plan.id, goal_key=goal.goal_key)
            session.add(row)
        for field, value in goal.model_dump().items():
            setattr(row, field, value)
    primary, scenarios = _primary_rows(session)
    if payload.primary_goal is not None:
        primary.name = payload.primary_goal.name
        primary.target_amount_inr = payload.primary_goal.target_amount_inr
        primary.deadline = payload.primary_goal.deadline
    for row, scenario in zip(scenarios, payload.scenarios):
        row.annual_return_pct = scenario.annual_return_pct
        row.monthly_contribution_inr = payload.assumptions.monthly_contribution_inr


def _save_family_plan(
    session: Session,
    payload: FamilyPlanUpdate,
    calculated_on: date,
    *,
    base_age: int | None = None,
) -> FamilyPlanResponse:
    fx = _resolve_opening_fx(session, calculated_on)
    transaction = session.begin_nested() if session.in_transaction() else session.begin()
    with transaction:
        plan = _plan(session)
        _apply(session, plan, payload, base_age=base_age)
        session.flush()
        return _family_plan_response(session, calculated_on, fx)


def save_family_plan(session: Session, payload: FamilyPlanUpdate, today: date | None = None) -> FamilyPlanResponse:
    calculated_on = today or date.today()
    payload.validate_target_dates(calculated_on)
    return _save_family_plan(session, payload, calculated_on)


def _defaults() -> FamilyPlanUpdate:
    goal_data = [
        ("child_1_education", "Child 1 education", "education", 20_000_000, date(2032,12,31), 8, "expense"),
        ("passive_income", "Passive income", "passive_income", 200_000, date(2029,12,31), 0, "income_target"),
        ("bangalore_house", "Bangalore house", "house", 30_000_000, date(2036,12,31), 8, "asset_conversion"),
        ("child_2_education", "Child 2 education", "education", 20_000_000, date(2038,12,31), 8, "expense"),
        ("child_1_marriage", "Child 1 marriage", "marriage", 5_000_000, date(2042,12,31), 6, "expense"),
        ("child_2_marriage", "Child 2 marriage", "marriage", 5_000_000, date(2044,12,31), 6, "expense"),
    ]
    return FamilyPlanUpdate.model_validate({
        "primary_goal": {"name": "₹15 Cr by 2029", "target_amount_inr": 150_000_000, "deadline": date(2029,12,31)},
        "assumptions": {"monthly_contribution_inr":600_000,"contribution_step_up_enabled":False,"contribution_step_up_pct":6,"monthly_rent_inr":45_000,"rent_growth_pct":6,"reinvest_rent_until":date(2029,12,31),"property_growth_pct":6,"withdrawal_rate_pct":3.5,"amber_margin_pct":10},
        "scenarios": [{"scenario_key":key,"annual_return_pct":rate} for key,rate in zip(SCENARIO_KEYS,(7,10,13))],
        "goals": [{"goal_key":key,"name":name,"goal_type":kind,"current_value_amount_inr":amount,"target_date":target,"inflation_pct":inflation,"funding_treatment":treatment,"priority":i+1,"enabled":True,"display_order":i} for i,(key,name,kind,amount,target,inflation,treatment) in enumerate(goal_data)],
    })


def restore_family_plan_defaults(session: Session, today: date | None = None) -> FamilyPlanResponse:
    calculated_on = today or date.today()
    payload = _defaults()
    payload.validate_target_dates(calculated_on)
    return _save_family_plan(session, payload, calculated_on, base_age=42)
