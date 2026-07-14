from datetime import date
import math

import pytest
from sqlalchemy import select

from app.repos.models import WealthGoal, WealthGoalScenario
from app.schemas.wealth_portfolio import GoalConfigurationUpdate
from app.services import wealth_goal_service
from app.services.wealth_goal_service import (
    monthly_trajectory,
    project_balance,
    projected_completion_date,
    required_monthly_contribution,
    whole_months_between,
    update_primary_goal,
)


def test_project_balance_at_zero_return_uses_end_of_period_contributions():
    assert project_balance(100_000, 0, 10_000, 12) == pytest.approx(220_000)


def test_project_balance_compounds_start_and_monthly_contributions():
    result = project_balance(10_000, 12, 1_000, 12)

    monthly_rate = 0.01
    growth = (1 + monthly_rate) ** 12
    expected = 10_000 * growth + 1_000 * ((growth - 1) / monthly_rate)
    assert result == pytest.approx(expected)


def test_required_contribution_is_zero_when_existing_wealth_reaches_target():
    assert required_monthly_contribution(100_000, 105_000, 12, 10) == 0


def test_required_contribution_reproduces_target():
    monthly = required_monthly_contribution(25_000, 75_000, 24, 7.5)

    assert project_balance(25_000, 7.5, monthly, 24) == pytest.approx(75_000)


@pytest.mark.parametrize("annual_return_pct", [1e-12, -1e-12])
def test_tiny_return_projection_converges_to_zero_rate_limit(annual_return_pct):
    assert project_balance(0, annual_return_pct, 1, 600) == pytest.approx(
        600, rel=1e-12
    )


@pytest.mark.parametrize("annual_return_pct", [1e-12, -1e-12])
def test_tiny_return_required_contribution_converges_to_zero_rate_limit(
    annual_return_pct,
):
    assert required_monthly_contribution(
        0, 600, 600, annual_return_pct
    ) == pytest.approx(1, rel=1e-12)


def test_whole_months_between_uses_complete_calendar_months():
    assert whole_months_between(date(2024, 1, 31), date(2024, 2, 29)) == 0
    assert whole_months_between(date(2024, 1, 15), date(2024, 3, 15)) == 2
    assert whole_months_between(date(2024, 1, 15), date(2024, 3, 14)) == 1


def test_monthly_trajectory_uses_real_month_ends_in_a_leap_year():
    points = monthly_trajectory(date(2024, 1, 30), 100, 0, 10, 3)

    assert [point.on for point in points] == [
        date(2024, 2, 29),
        date(2024, 3, 31),
        date(2024, 4, 30),
    ]
    assert [point.balance for point in points] == pytest.approx([110, 120, 130])


def test_completion_date_is_calculation_date_when_starting_at_goal():
    calculated_on = date(2026, 7, 14)
    assert projected_completion_date(calculated_on, 100, 100, 5, 0) == calculated_on


def test_completion_date_is_first_month_end_that_reaches_target():
    assert projected_completion_date(date(2024, 1, 30), 100, 130, 0, 10) == date(
        2024, 4, 30
    )


def test_completion_date_is_none_when_target_is_unreachable_within_fifty_years():
    assert projected_completion_date(date(2024, 1, 1), 0, 1, 0, 0) is None


@pytest.mark.parametrize("months", [0, -1])
def test_projection_functions_reject_nonpositive_months(months):
    with pytest.raises(ValueError):
        project_balance(100, 5, 10, months)
    with pytest.raises(ValueError):
        required_monthly_contribution(100, 200, months, 5)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_projection_functions_reject_nonfinite_inputs(value):
    with pytest.raises(ValueError):
        project_balance(value, 5, 10, 12)
    with pytest.raises(ValueError):
        required_monthly_contribution(100, value, 12, 5)


def test_projection_rejects_negative_contribution_and_invalid_monthly_rate():
    with pytest.raises(ValueError):
        project_balance(100, 5, -1, 12)
    with pytest.raises(ValueError):
        project_balance(100, -1200, 1, 12)
    with pytest.raises(ValueError):
        required_monthly_contribution(100, 200, 12, -1200)


@pytest.mark.parametrize(
    ("start", "annual_return_pct", "monthly", "months"),
    [
        (0, 0, 1e308, 12),
        (1e308, 50, 0, 600),
    ],
)
def test_project_balance_rejects_nonfinite_calculation_results(
    start, annual_return_pct, monthly, months
):
    with pytest.raises(ValueError, match="finite projection"):
        project_balance(start, annual_return_pct, monthly, months)


def test_monthly_trajectory_rejects_nonfinite_balance():
    with pytest.raises(ValueError, match="finite projection"):
        monthly_trajectory(date(2026, 7, 14), 0, 0, 1e308, 12)


def test_calendar_helpers_reject_reversed_dates_and_invalid_trajectory_inputs():
    with pytest.raises(ValueError):
        whole_months_between(date(2024, 2, 1), date(2024, 1, 31))
    with pytest.raises(ValueError):
        monthly_trajectory(date(2024, 1, 1), 100, 5, -1, 12)


def test_update_rolls_back_when_recalculation_fails_after_mutation(
    session, monkeypatch
):
    payload = GoalConfigurationUpdate.model_validate(
        {
            "goal": {
                "name": "Changed goal",
                "target_amount_inr": 200_000_000,
                "deadline": "2035-12-31",
            },
            "scenarios": [
                {
                    "scenario_key": "conservative",
                    "annual_return_pct": 8,
                    "monthly_contribution_inr": 1,
                },
                {
                    "scenario_key": "expected",
                    "annual_return_pct": 11,
                    "monthly_contribution_inr": 2,
                },
                {
                    "scenario_key": "optimistic",
                    "annual_return_pct": 14,
                    "monthly_contribution_inr": 3,
                },
            ],
        }
    )

    def fail_recalculation(*args, **kwargs):
        raise RuntimeError("forced recalculation failure")

    monkeypatch.setattr(
        wealth_goal_service, "get_primary_goal_response", fail_recalculation
    )

    with pytest.raises(RuntimeError, match="forced recalculation failure"):
        update_primary_goal(session, payload, today=date(2026, 7, 14))

    session.expire_all()
    goal = session.scalar(select(WealthGoal).where(WealthGoal.is_primary.is_(True)))
    scenarios = list(
        session.scalars(
            select(WealthGoalScenario)
            .where(WealthGoalScenario.goal_id == goal.id)
            .order_by(WealthGoalScenario.display_order)
        )
    )
    assert goal.name == "₹15 Cr by 2029"
    assert goal.target_amount_inr == 150_000_000
    assert [scenario.annual_return_pct for scenario in scenarios] == [7, 10, 13]
