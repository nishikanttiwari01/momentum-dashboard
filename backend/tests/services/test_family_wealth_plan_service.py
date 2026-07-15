from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas.wealth_portfolio import FamilyPlanUpdate


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
