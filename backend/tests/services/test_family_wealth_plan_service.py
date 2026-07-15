from datetime import date
import math

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.repos.models import (
    FamilyWealthGoal,
    PortfolioAsset,
    PortfolioFxRate,
    PortfolioImport,
    PortfolioSnapshot,
    WealthGoal,
    WealthGoalScenario,
)
from app.services import family_wealth_plan_service
from app.services.family_wealth_plan_service import (
    get_family_plan_response,
    restore_family_plan_defaults,
    save_family_plan,
)

from app.schemas.wealth_portfolio import (
    AnnualRunwayEvent,
    AnnualRunwayPoint,
    FamilyPlanResponse,
    FamilyPlanUpdate,
    FamilyScenarioProjection,
    GoalHealth,
    PassiveIncomeAnalysis,
)


def _payload() -> dict:
    return {
        "assumptions": {
            "monthly_contribution_inr": 100_000,
            "contribution_step_up_enabled": True,
            "contribution_step_up_pct": 5,
            "monthly_rent_inr": 30_000,
            "rent_growth_pct": 5,
            "reinvest_rent_until": date(2030, 1, 1),
            "property_growth_pct": 6,
            "withdrawal_rate_pct": 4,
            "amber_margin_pct": 10,
        },
        "scenarios": [
            {"scenario_key": "conservative", "annual_return_pct": 6},
            {"scenario_key": "expected", "annual_return_pct": 9},
            {"scenario_key": "optimistic", "annual_return_pct": 12},
        ],
        "goals": [
            {
                "goal_key": "child_education",
                "name": "Child education",
                "goal_type": "education",
                "current_value_amount_inr": 5_000_000,
                "target_date": date(2035, 6, 1),
                "inflation_pct": 7,
                "funding_treatment": "expense",
                "priority": 10,
                "enabled": True,
                "display_order": 1,
            }
        ],
    }


def _add_snapshot(session, *, snapshot_id="snapshot-1", as_of=date(2026, 7, 1), assets=()):
    import_id = f"import-{snapshot_id}"
    session.add(PortfolioImport(id=import_id, source_sha256=import_id, filename="book.xlsx", status="completed", issue_counts={}))
    session.add(PortfolioSnapshot(id=snapshot_id, import_id=import_id, as_of=as_of))
    for index, asset in enumerate(assets):
        session.add(PortfolioAsset(
            id=f"{snapshot_id}-asset-{index}", snapshot_id=snapshot_id,
            source_key=f"key-{index}", name=f"Asset {index}", market="INDIA",
            source_ref={}, **asset,
        ))
    session.commit()


def test_service_uses_latest_snapshot_and_splits_property_without_double_count(session, monkeypatch):
    _add_snapshot(session, snapshot_id="old", as_of=date(2026, 6, 1), assets=[dict(asset_type="stocks", currency="INR", invested_amount=1, market_value=999)])
    _add_snapshot(session, snapshot_id="new", assets=[
        dict(asset_type="stocks", currency="INR", invested_amount=80, market_value=100),
        dict(asset_type="property", currency="INR", invested_amount=150, market_value=200),
        dict(asset_type="land", currency="INR", invested_amount=250, market_value=300),
    ])

    captured = []
    real_project = family_wealth_plan_service.project_family_wealth
    monkeypatch.setattr(family_wealth_plan_service, "project_family_wealth", lambda data: (captured.append(data), real_project(data))[1])
    response = get_family_plan_response(session, today=date(2026, 7, 15))

    assert response.snapshot_id == "new"
    assert response.data_health == "fresh"
    assert len(captured) == 3
    assert captured[0].opening_financial == 100
    assert captured[0].opening_property == 500


def test_service_converts_usd_and_warns_when_fx_is_missing(session, monkeypatch):
    _add_snapshot(session, assets=[dict(asset_type="us_holdings", currency="USD", invested_amount=8, market_value=10)])
    captured = []
    real_project = family_wealth_plan_service.project_family_wealth
    monkeypatch.setattr(family_wealth_plan_service, "project_family_wealth", lambda data: (captured.append(data), real_project(data))[1])
    response = get_family_plan_response(session, today=date(2026, 7, 15))
    assert response.data_health in {"warning", "unavailable"}
    assert captured[0].opening_financial == 0

    session.add(PortfolioFxRate(base_currency="USD", quote_currency="INR", effective_on=date(2026, 7, 1), rate=85, source="test", fetched_at=date(2026, 7, 1)))
    session.commit()
    captured.clear()
    converted = get_family_plan_response(session, today=date(2026, 7, 15))
    assert converted.data_health == "fresh"
    assert captured[0].opening_financial == 850


def test_service_does_not_substitute_invested_amount_for_missing_market_value(session, monkeypatch):
    _add_snapshot(session, assets=[dict(asset_type="stocks", currency="INR", invested_amount=50_000, market_value=None)])
    captured = []
    real_project = family_wealth_plan_service.project_family_wealth
    monkeypatch.setattr(family_wealth_plan_service, "project_family_wealth", lambda data: (captured.append(data), real_project(data))[1])

    get_family_plan_response(session, today=date(2026, 7, 15))

    assert captured[0].opening_financial == 0


def test_empty_snapshot_returns_configured_three_scenarios(session):
    response = get_family_plan_response(session, today=date(2026, 7, 15))
    assert response.snapshot_id is None
    assert response.data_health == "empty"
    assert len(response.scenario_projections) == 3
    assert all(item.ending_total_net_worth_inr >= 0 for item in response.scenario_projections)
    FamilyPlanResponse.model_validate(response.model_dump())


def test_save_validates_dates_persists_and_synchronizes_primary_scenarios(session, monkeypatch):
    payload = FamilyPlanUpdate.model_validate(_payload())
    called = []
    original = FamilyPlanUpdate.validate_target_dates
    monkeypatch.setattr(FamilyPlanUpdate, "validate_target_dates", lambda self, day: (called.append(day), original(self, day))[1])

    response = save_family_plan(session, payload, today=date(2026, 7, 15))

    assert called == [date(2026, 7, 15)]
    assert response.assumptions.monthly_contribution_inr == 100_000
    primary = session.scalar(select(WealthGoal).where(WealthGoal.is_primary.is_(True)))
    rows = list(session.scalars(select(WealthGoalScenario).where(WealthGoalScenario.goal_id == primary.id)))
    assert {row.monthly_contribution_inr for row in rows} == {100_000}


def test_save_failure_rolls_back_plan_goals_and_scenarios(session, monkeypatch):
    before = get_family_plan_response(session, today=date(2026, 7, 15))
    payload = FamilyPlanUpdate.model_validate(_payload())
    monkeypatch.setattr(family_wealth_plan_service, "project_family_wealth", lambda *_: (_ for _ in ()).throw(RuntimeError("forced")))
    with pytest.raises(RuntimeError, match="forced"):
        save_family_plan(session, payload, today=date(2026, 7, 15))
    monkeypatch.undo()
    session.expire_all()
    after = get_family_plan_response(session, today=date(2026, 7, 15))
    assert after.assumptions == before.assumptions
    assert after.goals == before.goals


def test_goal_replacement_preserves_existing_id_and_assigns_stable_new_id(session):
    existing = session.scalar(select(FamilyWealthGoal).where(FamilyWealthGoal.goal_key == "child_1_education"))
    payload = _payload()
    payload["goals"] = [payload["goals"][0], {**payload["goals"][0], "goal_key": "new_house", "name": "New house", "goal_type": "house", "funding_treatment": "asset_conversion", "display_order": 0}]
    saved = save_family_plan(session, FamilyPlanUpdate.model_validate(payload), today=date(2026, 7, 15))
    ids = {row.goal_key: row.id for row in session.scalars(select(FamilyWealthGoal))}
    assert "child_1_education" not in ids
    assert [g.goal_key for g in saved.goals] == ["new_house", "child_education"]
    first_new_id = ids["new_house"]
    save_family_plan(session, FamilyPlanUpdate.model_validate(payload), today=date(2026, 7, 15))
    assert session.scalar(select(FamilyWealthGoal.id).where(FamilyWealthGoal.goal_key == "new_house")) == first_new_id


def test_restore_family_plan_defaults_exactly(session):
    save_family_plan(session, FamilyPlanUpdate.model_validate(_payload()), today=date(2026, 7, 15))
    restored = restore_family_plan_defaults(session, today=date(2026, 7, 15))
    assert restored.assumptions.monthly_contribution_inr == 600_000
    assert restored.assumptions.reinvest_rent_until == date(2029, 12, 31)
    assert [p.settings.annual_return_pct for p in restored.scenario_projections] == [7, 10, 13]
    assert [g.goal_key for g in restored.goals] == ["child_1_education", "passive_income", "bangalore_house", "child_2_education", "child_1_marriage", "child_2_marriage"]


def _error_locations(payload: dict) -> list[tuple]:
    with pytest.raises(ValidationError) as exc_info:
        FamilyPlanUpdate.model_validate(payload)
    return [error["loc"] for error in exc_info.value.errors()]


def test_rejects_duplicate_goal_keys_at_stable_goals_location() -> None:
    payload = _payload()
    payload["goals"].append({**payload["goals"][0], "display_order": 2})

    assert _error_locations(payload) == [("goals",)]


def test_allows_duplicate_display_order_for_later_tie_breaking() -> None:
    payload = _payload()
    payload["goals"].append(
        {
            **payload["goals"][0],
            "goal_key": "child_marriage",
            "name": "Child marriage",
            "goal_type": "marriage",
        }
    )

    assert len(FamilyPlanUpdate.model_validate(payload).goals) == 2


def test_rejects_zero_withdrawal_rate() -> None:
    payload = _payload()
    payload["assumptions"]["withdrawal_rate_pct"] = 0

    assert ("assumptions", "withdrawal_rate_pct") in _error_locations(payload)


@pytest.mark.parametrize(
    "scenarios, location",
    [
        (
            [
                {"scenario_key": "expected", "annual_return_pct": 9},
                {"scenario_key": "conservative", "annual_return_pct": 6},
                {"scenario_key": "optimistic", "annual_return_pct": 12},
            ],
            ("scenarios", 0, "scenario_key"),
        ),
        (
            [
                {"scenario_key": "conservative", "annual_return_pct": 10},
                {"scenario_key": "expected", "annual_return_pct": 9},
                {"scenario_key": "optimistic", "annual_return_pct": 12},
            ],
            ("scenarios", 1, "annual_return_pct"),
        ),
    ],
)
def test_requires_ordered_scenarios_and_nondecreasing_returns(
    scenarios: list[dict], location: tuple
) -> None:
    payload = _payload()
    payload["scenarios"] = scenarios

    assert location in _error_locations(payload)


@pytest.mark.parametrize(
    "goal_type,treatment",
    [
        ("house", "expense"),
        ("passive_income", "expense"),
        ("education", "asset_conversion"),
        ("marriage", "income_target"),
    ],
)
def test_rejects_goal_type_funding_treatment_mismatch(
    goal_type: str, treatment: str
) -> None:
    payload = _payload()
    payload["goals"][0]["goal_type"] = goal_type
    payload["goals"][0]["funding_treatment"] = treatment

    assert ("goals", 0, "funding_treatment") in _error_locations(payload)


@pytest.mark.parametrize(
    "path,value",
    [
        (("assumptions", "monthly_contribution_inr"), float("inf")),
        (("assumptions", "monthly_rent_inr"), 1_000_000_001),
        (("scenarios", 0, "annual_return_pct"), float("nan")),
        (("goals", 0, "current_value_amount_inr"), 1_000_000_000_000_001),
    ],
)
def test_rejects_nonfinite_and_out_of_range_values(path: tuple, value: float) -> None:
    payload = _payload()
    target = payload
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value

    assert path in _error_locations(payload)


def test_accepts_valid_family_plan_contract() -> None:
    plan = FamilyPlanUpdate.model_validate(_payload())

    assert [scenario.scenario_key for scenario in plan.scenarios] == [
        "conservative",
        "expected",
        "optimistic",
    ]


@pytest.mark.parametrize(
    "field,value",
    [("goal_type", "retirement"), ("funding_treatment", "investment")],
)
def test_rejects_values_outside_goal_and_treatment_literals(
    field: str, value: str
) -> None:
    payload = _payload()
    payload["goals"][0][field] = value

    assert ("goals", 0, field) in _error_locations(payload)


@pytest.mark.parametrize("goal_key", ["Upper_Case", "has-dash", "x" * 41])
def test_rejects_invalid_goal_keys(goal_key: str) -> None:
    payload = _payload()
    payload["goals"][0]["goal_key"] = goal_key

    assert ("goals", 0, "goal_key") in _error_locations(payload)


@pytest.mark.parametrize("scenario_count", [2, 4])
def test_requires_exactly_three_scenarios(scenario_count: int) -> None:
    payload = _payload()
    payload["scenarios"] = (
        payload["scenarios"][:scenario_count]
        if scenario_count < 3
        else payload["scenarios"] + [payload["scenarios"][-1]]
    )

    assert ("scenarios",) in _error_locations(payload)


@pytest.mark.parametrize("annual_return_pct", [-25, 50])
def test_accepts_family_scenario_return_boundaries(
    annual_return_pct: float,
) -> None:
    payload = _payload()
    payload["scenarios"] = [
        {"scenario_key": "conservative", "annual_return_pct": annual_return_pct},
        {"scenario_key": "expected", "annual_return_pct": annual_return_pct},
        {"scenario_key": "optimistic", "annual_return_pct": annual_return_pct},
    ]

    assert all(
        scenario.annual_return_pct == annual_return_pct
        for scenario in FamilyPlanUpdate.model_validate(payload).scenarios
    )


@pytest.mark.parametrize("annual_return_pct", [-25.01, 50.01])
def test_rejects_family_scenario_returns_outside_bounds(
    annual_return_pct: float,
) -> None:
    payload = _payload()
    payload["scenarios"][1]["annual_return_pct"] = annual_return_pct

    assert ("scenarios", 1, "annual_return_pct") in _error_locations(payload)


@pytest.mark.parametrize(
    "field,lower,upper",
    [
        ("monthly_contribution_inr", 0, 1_000_000_000_000),
        ("contribution_step_up_pct", 0, 25),
        ("monthly_rent_inr", 0, 1_000_000_000),
        ("rent_growth_pct", -25, 50),
        ("property_growth_pct", -25, 50),
        ("withdrawal_rate_pct", 0.01, 20),
        ("amber_margin_pct", 0, 100),
    ],
)
def test_accepts_family_assumption_numeric_boundaries(
    field: str, lower: float, upper: float
) -> None:
    for value in (lower, upper):
        payload = _payload()
        payload["assumptions"][field] = value
        assert getattr(FamilyPlanUpdate.model_validate(payload).assumptions, field) == value


@pytest.mark.parametrize(
    "field,value",
    [
        ("monthly_contribution_inr", -0.01),
        ("monthly_contribution_inr", 1_000_000_000_001),
        ("contribution_step_up_pct", -0.01),
        ("contribution_step_up_pct", 25.01),
        ("monthly_rent_inr", -0.01),
        ("monthly_rent_inr", 1_000_000_001),
        ("rent_growth_pct", -25.01),
        ("rent_growth_pct", 50.01),
        ("property_growth_pct", -25.01),
        ("property_growth_pct", 50.01),
        ("withdrawal_rate_pct", 0),
        ("withdrawal_rate_pct", 20.01),
        ("amber_margin_pct", -0.01),
        ("amber_margin_pct", 100.01),
    ],
)
def test_rejects_family_assumption_values_outside_bounds(
    field: str, value: float
) -> None:
    payload = _payload()
    payload["assumptions"][field] = value
    assert ("assumptions", field) in _error_locations(payload)


@pytest.mark.parametrize(
    "field,lower,upper",
    [
        ("current_value_amount_inr", 0.01, 1_000_000_000_000_000),
        ("inflation_pct", 0, 25),
        ("priority", 1, 100),
        ("display_order", 0, 100),
    ],
)
def test_accepts_linked_goal_numeric_boundaries(
    field: str, lower: float, upper: float
) -> None:
    for value in (lower, upper):
        payload = _payload()
        payload["goals"][0][field] = value
        assert getattr(FamilyPlanUpdate.model_validate(payload).goals[0], field) == value


@pytest.mark.parametrize(
    "field,value",
    [
        ("current_value_amount_inr", 0),
        ("current_value_amount_inr", 1_000_000_000_000_001),
        ("inflation_pct", -0.01),
        ("inflation_pct", 25.01),
        ("priority", 0),
        ("priority", 101),
        ("display_order", -1),
        ("display_order", 101),
    ],
)
def test_rejects_linked_goal_values_outside_bounds(field: str, value: float) -> None:
    payload = _payload()
    payload["goals"][0][field] = value
    assert ("goals", 0, field) in _error_locations(payload)


def _response_parts() -> tuple:
    plan = FamilyPlanUpdate.model_validate(_payload())
    event = AnnualRunwayEvent(
        goal_key="child_education",
        goal_name="Child education",
        goal_type="education",
        funding_treatment="expense",
        amount_inr=6_000_000,
        funded_amount_inr=5_500_000,
        shortfall_inr=500_000,
    )
    point = AnnualRunwayPoint(
        on=date(2035, 12, 31),
        financial_assets_inr=20_000_000,
        property_value_inr=15_000_000,
        total_net_worth_inr=35_000_000,
        annual_contributions_inr=1_200_000,
        annual_rent_inr=480_000,
        financial_growth_inr=1_500_000,
        property_growth_inr=900_000,
        goal_outflows_inr=5_500_000,
        events=[event],
    )
    health = GoalHealth(
        goal=plan.goals[0],
        inflated_cost_inr=6_000_000,
        available_before_inr=5_500_000,
        funded_amount_inr=5_500_000,
        shortfall_inr=500_000,
        funded_pct=91.67,
        status="amber",
        reason="Within the configured amber margin",
    )
    passive = PassiveIncomeAnalysis(
        target_date=date(2040, 1, 1),
        target_monthly_income_inr=200_000,
        projected_monthly_rent_inr=80_000,
        portfolio_monthly_gap_inr=120_000,
        required_corpus_inr=36_000_000,
        supported_portfolio_monthly_income_inr=110_000,
        total_monthly_income_inr=190_000,
        surplus_or_shortfall_inr=-10_000,
        on_track=False,
        later_goals_protected=True,
        earliest_sustainable_date=date(2041, 6, 1),
    )
    projection = FamilyScenarioProjection(
        settings=plan.scenarios[1],
        annual_points=[point],
        goal_health=[health],
        passive_income=passive,
        ending_financial_assets_inr=25_000_000,
        ending_property_value_inr=18_000_000,
        ending_total_net_worth_inr=43_000_000,
        first_underfunded_goal_key="child_education",
    )
    return plan, event, point, health, passive, projection


def test_constructs_complete_family_plan_response_contract() -> None:
    plan, event, point, health, passive, projection = _response_parts()
    projections = [
        projection.model_copy(update={"settings": scenario})
        for scenario in plan.scenarios
    ]
    response = FamilyPlanResponse(
        primary_goal={
            "goal": {
                "name": "Family corpus",
                "target_amount_inr": 50_000_000,
                "deadline": date(2045, 1, 1),
            },
            "scenario_projections": [],
            "calculated_on": date(2026, 7, 15),
        },
        calculated_on=date(2026, 7, 15),
        snapshot_id="snapshot-1",
        data_health="fresh",
        assumptions=plan.assumptions,
        goals=plan.goals,
        scenario_projections=projections,
    )

    assert response.primary_goal.goal.name == "Family corpus"
    assert response.assumptions.monthly_contribution_inr == 100_000
    assert response.goals[0].goal_key == "child_education"
    assert [item.settings.scenario_key for item in response.scenario_projections] == [
        "conservative",
        "expected",
        "optimistic",
    ]
    assert point.events == [event]
    assert event.funded_amount_inr == 5_500_000
    assert point.total_net_worth_inr == 35_000_000
    assert health.shortfall_inr == 500_000
    assert passive.required_corpus_inr == 36_000_000
    assert projection.ending_total_net_worth_inr == 43_000_000


@pytest.mark.parametrize(
    "model,field",
    [
        (AnnualRunwayEvent, "amount_inr"),
        (AnnualRunwayPoint, "financial_assets_inr"),
        (GoalHealth, "inflated_cost_inr"),
        (PassiveIncomeAnalysis, "required_corpus_inr"),
        (FamilyScenarioProjection, "ending_total_net_worth_inr"),
    ],
)
def test_response_contracts_reject_nonfinite_monetary_values(model, field: str) -> None:
    _, event, point, health, passive, projection = _response_parts()
    instance = {
        AnnualRunwayEvent: event,
        AnnualRunwayPoint: point,
        GoalHealth: health,
        PassiveIncomeAnalysis: passive,
        FamilyScenarioProjection: projection,
    }[model]
    payload = instance.model_dump()
    payload[field] = float("nan")

    with pytest.raises(ValidationError) as exc_info:
        model.model_validate(payload)
    assert (field,) in [error["loc"] for error in exc_info.value.errors()]


@pytest.mark.parametrize(
    "model,field",
    [
        (AnnualRunwayEvent, "amount_inr"),
        (AnnualRunwayEvent, "funded_amount_inr"),
        (AnnualRunwayPoint, "financial_assets_inr"),
        (AnnualRunwayPoint, "annual_contributions_inr"),
        (GoalHealth, "shortfall_inr"),
        (GoalHealth, "funded_pct"),
        (PassiveIncomeAnalysis, "required_corpus_inr"),
        (FamilyScenarioProjection, "ending_property_value_inr"),
    ],
)
def test_response_contracts_reject_negative_nonnegative_values(model, field: str) -> None:
    _, event, point, health, passive, projection = _response_parts()
    instance = {
        AnnualRunwayEvent: event,
        AnnualRunwayPoint: point,
        GoalHealth: health,
        PassiveIncomeAnalysis: passive,
        FamilyScenarioProjection: projection,
    }[model]
    payload = instance.model_dump()
    payload[field] = -0.01

    with pytest.raises(ValidationError) as exc_info:
        model.model_validate(payload)
    assert (field,) in [error["loc"] for error in exc_info.value.errors()]


def test_goal_health_rejects_funded_pct_above_100() -> None:
    _, _, _, health, _, _ = _response_parts()
    payload = health.model_dump()
    payload["funded_pct"] = 100.01
    with pytest.raises(ValidationError) as exc_info:
        GoalHealth.model_validate(payload)
    assert ("funded_pct",) in [error["loc"] for error in exc_info.value.errors()]


@pytest.mark.parametrize(
    "model,field",
    [
        (AnnualRunwayEvent, "shortfall_inr"),
        (AnnualRunwayPoint, "total_net_worth_inr"),
        (GoalHealth, "shortfall_inr"),
        (FamilyScenarioProjection, "ending_total_net_worth_inr"),
    ],
)
def test_response_contracts_reject_contradictory_financial_totals(
    model, field: str
) -> None:
    _, event, point, health, _, projection = _response_parts()
    instance = {
        AnnualRunwayEvent: event,
        AnnualRunwayPoint: point,
        GoalHealth: health,
        FamilyScenarioProjection: projection,
    }[model]
    payload = instance.model_dump()
    payload[field] += 0.02
    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_financial_consistency_allows_one_cent_rounding_tolerance() -> None:
    _, event, _, _, _, _ = _response_parts()
    payload = event.model_dump()
    payload["shortfall_inr"] += 0.01
    assert AnnualRunwayEvent.model_validate(payload).shortfall_inr == 500_000.01


def _family_response_payload() -> dict:
    plan, _, _, _, _, projection = _response_parts()
    projections = [
        projection.model_copy(update={"settings": scenario})
        for scenario in plan.scenarios
    ]
    return {
        "primary_goal": {
            "goal": {
                "name": "Family corpus",
                "target_amount_inr": 50_000_000,
                "deadline": date(2045, 1, 1),
            },
            "scenario_projections": [],
            "calculated_on": date(2026, 7, 15),
        },
        "calculated_on": date(2026, 7, 15),
        "snapshot_id": "snapshot-1",
        "data_health": "fresh",
        "assumptions": plan.assumptions,
        "goals": plan.goals,
        "scenario_projections": projections,
    }


@pytest.mark.parametrize("projection_count", [2, 4])
def test_family_response_requires_exactly_three_scenarios(
    projection_count: int,
) -> None:
    payload = _family_response_payload()
    payload["scenario_projections"] = (
        payload["scenario_projections"][:projection_count]
        if projection_count < 3
        else payload["scenario_projections"] + [payload["scenario_projections"][-1]]
    )
    with pytest.raises(ValidationError) as exc_info:
        FamilyPlanResponse.model_validate(payload)
    assert ("scenario_projections",) in [e["loc"] for e in exc_info.value.errors()]


def test_family_response_requires_scenarios_in_canonical_order() -> None:
    payload = _family_response_payload()
    payload["scenario_projections"][0], payload["scenario_projections"][1] = (
        payload["scenario_projections"][1],
        payload["scenario_projections"][0],
    )
    with pytest.raises(ValidationError) as exc_info:
        FamilyPlanResponse.model_validate(payload)
    assert ("scenario_projections", 0, "settings", "scenario_key") in [
        e["loc"] for e in exc_info.value.errors()
    ]


def test_family_response_rejects_duplicate_goal_keys() -> None:
    payload = _family_response_payload()
    payload["goals"].append(payload["goals"][0])
    with pytest.raises(ValidationError) as exc_info:
        FamilyPlanResponse.model_validate(payload)
    assert ("goals",) in [e["loc"] for e in exc_info.value.errors()]


@pytest.mark.parametrize("target_date", [date(2026, 7, 14), date(2026, 7, 15)])
def test_enabled_goal_rejects_target_date_on_or_before_reference_date(
    target_date: date,
) -> None:
    plan = FamilyPlanUpdate.model_validate(_payload())
    plan.goals[0].target_date = target_date
    with pytest.raises(ValidationError) as exc_info:
        plan.validate_target_dates(date(2026, 7, 15))
    assert ("goals", 0, "target_date") in [
        error["loc"] for error in exc_info.value.errors()
    ]


def test_enabled_goal_accepts_target_date_after_reference_date() -> None:
    plan = FamilyPlanUpdate.model_validate(_payload())
    plan.goals[0].target_date = date(2026, 7, 16)
    assert plan.validate_target_dates(date(2026, 7, 15)) is plan


def test_disabled_goal_may_retain_historical_target_date() -> None:
    payload = _payload()
    payload["goals"][0]["enabled"] = False
    payload["goals"][0]["target_date"] = date(2020, 1, 1)
    plan = FamilyPlanUpdate.model_validate(payload)
    assert plan.validate_target_dates(date(2026, 7, 15)) is plan


def test_numeric_strings_are_intentionally_coerced_for_api_form_ergonomics() -> None:
    payload = _payload()
    payload["assumptions"]["monthly_contribution_inr"] = "100000"
    payload["goals"][0]["priority"] = "10"
    plan = FamilyPlanUpdate.model_validate(payload)
    assert plan.assumptions.monthly_contribution_inr == 100_000
    assert plan.goals[0].priority == 10


@pytest.mark.parametrize(
    "model,total_field,component_fields",
    [
        (AnnualRunwayEvent, "amount_inr", ("funded_amount_inr", "shortfall_inr")),
        (
            AnnualRunwayPoint,
            "total_net_worth_inr",
            ("financial_assets_inr", "property_value_inr"),
        ),
        (GoalHealth, "inflated_cost_inr", ("funded_amount_inr", "shortfall_inr")),
        (
            FamilyScenarioProjection,
            "ending_total_net_worth_inr",
            ("ending_financial_assets_inr", "ending_property_value_inr"),
        ),
    ],
)
def test_financial_consistency_tolerates_large_value_float_ulp(
    model, total_field: str, component_fields: tuple[str, str]
) -> None:
    _, event, point, health, _, projection = _response_parts()
    instance = {
        AnnualRunwayEvent: event,
        AnnualRunwayPoint: point,
        GoalHealth: health,
        FamilyScenarioProjection: projection,
    }[model]
    payload = instance.model_dump()
    payload[component_fields[0]] = 600_000_000_000_000.0
    payload[component_fields[1]] = 400_000_000_000_000.0
    payload[total_field] = math.nextafter(1_000_000_000_000_000.0, math.inf)

    assert getattr(model.model_validate(payload), total_field) == payload[total_field]


def test_family_response_validation_error_uses_response_model_title() -> None:
    payload = _family_response_payload()
    payload["scenario_projections"] = payload["scenario_projections"][:2]
    with pytest.raises(ValidationError) as exc_info:
        FamilyPlanResponse.model_validate(payload)
    assert exc_info.value.title == "FamilyPlanResponse"
