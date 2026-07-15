from datetime import date, timedelta

import pytest
from pydantic import ValidationError

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


def test_enabled_goal_requires_future_target_date() -> None:
    payload = _payload()
    payload["goals"][0]["target_date"] = date.today()
    assert ("goals", 0, "target_date") in _error_locations(payload)


def test_disabled_goal_may_retain_historical_target_date() -> None:
    payload = _payload()
    payload["goals"][0]["enabled"] = False
    payload["goals"][0]["target_date"] = date.today() - timedelta(days=1)
    assert FamilyPlanUpdate.model_validate(payload).goals[0].enabled is False


def test_numeric_strings_are_intentionally_coerced_for_api_form_ergonomics() -> None:
    payload = _payload()
    payload["assumptions"]["monthly_contribution_inr"] = "100000"
    payload["goals"][0]["priority"] = "10"
    plan = FamilyPlanUpdate.model_validate(payload)
    assert plan.assumptions.monthly_contribution_inr == 100_000
    assert plan.goals[0].priority == 10
