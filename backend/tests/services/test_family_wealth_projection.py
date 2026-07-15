from dataclasses import FrozenInstanceError, replace
from datetime import date
from decimal import Decimal
import math

import pytest

from app.services.family_wealth_projection import (
    ProjectionGoal,
    ProjectionInput,
    UnsafeProjection,
    project_family_wealth,
)


D = Decimal


def _input(**overrides) -> ProjectionInput:
    values = dict(
        calculated_on=date(2026, 12, 1),
        end_date=date(2027, 2, 28),
        opening_financial=D("1000000"),
        opening_property=D("2000000"),
        monthly_contribution=D("600000"),
        contribution_step_up_enabled=False,
        contribution_step_up_pct=D("6"),
        monthly_rent=D("10000"),
        rent_growth_pct=D("10"),
        reinvest_rent_until=date(2027, 12, 31),
        property_growth_pct=D("0"),
        withdrawal_rate_pct=D("4"),
        amber_margin_pct=D("10"),
        annual_financial_return_pct=D("0"),
        goals=(),
    )
    values.update(overrides)
    return ProjectionInput(**values)


def _goal(key: str, treatment: str = "expense", **overrides) -> ProjectionGoal:
    values = dict(
        key=key,
        name=key.replace("_", " ").title(),
        goal_type="education",
        funding_treatment=treatment,
        current_value_amount=D("100000"),
        target_date=date(2027, 1, 1),
        inflation_pct=D("0"),
        priority=10,
        enabled=True,
    )
    values.update(overrides)
    return ProjectionGoal(**values)


def test_flat_contribution_and_january_step_up() -> None:
    flat = project_family_wealth(_input())
    stepped = project_family_wealth(
        _input(contribution_step_up_enabled=True)
    )

    assert [p.contribution for p in flat.monthly_points] == [D("600000.00")] * 3
    assert [p.contribution for p in stepped.monthly_points] == [
        D("600000.00"), D("636000.00"), D("636000.00")
    ]


def test_rent_growth_and_reinvestment_cutoff() -> None:
    result = project_family_wealth(
        _input(reinvest_rent_until=date(2027, 1, 15))
    )

    assert [p.projected_monthly_rent for p in result.monthly_points] == [
        D("10000.00"), D("11000.00"), D("11000.00")
    ]
    assert [p.reinvested_rent for p in result.monthly_points] == [
        D("10000.00"), D("11000.00"), D("0.00")
    ]


def test_inflation_adjusts_goal_cost_by_months_to_target() -> None:
    goal = _goal(
        "school", current_value_amount=D("120000"),
        inflation_pct=D("12"), target_date=date(2027, 12, 1)
    )
    result = project_family_wealth(
        _input(end_date=date(2027, 12, 31), monthly_contribution=D("0"),
               monthly_rent=D("0"), goals=(goal,))
    )

    expected = (D("120000") * (D("1.12") ** (D(12) / D(12)))).quantize(D("0.01"))
    assert result.goal_results[0].inflated_cost == expected


def test_expenses_reduce_financial_assets_permanently() -> None:
    goals = (
        _goal("education", current_value_amount=D("100000")),
        _goal("marriage", goal_type="marriage", current_value_amount=D("200000"), priority=20),
    )
    result = project_family_wealth(
        _input(opening_financial=D("500000"), opening_property=D("0"),
               monthly_contribution=D("0"), monthly_rent=D("0"), goals=goals)
    )
    january = result.monthly_points[1]
    assert january.goal_outflows == D("300000.00")
    assert january.closing_financial == D("200000.00")
    assert result.ending_total == D("200000.00")


def test_house_conversion_moves_value_without_artificial_net_worth_loss() -> None:
    house = _goal("house", "asset_conversion", goal_type="house", current_value_amount=D("250000"))
    result = project_family_wealth(
        _input(opening_financial=D("500000"), opening_property=D("100000"),
               monthly_contribution=D("0"), monthly_rent=D("0"), goals=(house,))
    )
    january = result.monthly_points[1]
    assert january.closing_financial == D("250000.00")
    assert january.closing_property == D("350000.00")
    assert january.total_net_worth == D("600000.00")


def test_same_month_events_use_priority_then_key_order() -> None:
    goals = (
        _goal("z_last", priority=20, current_value_amount=D("100")),
        _goal("b_second", priority=10, current_value_amount=D("100")),
        _goal("a_first", priority=10, current_value_amount=D("100")),
    )
    result = project_family_wealth(_input(goals=goals, monthly_contribution=D("0"), monthly_rent=D("0")))
    assert [event.goal_key for event in result.monthly_points[1].events] == [
        "a_first", "b_second", "z_last"
    ]


def test_underfunded_event_floors_at_zero_and_later_inflows_rebuild() -> None:
    goal = _goal("too_large", current_value_amount=D("150"))
    result = project_family_wealth(
        _input(opening_financial=D("100"), opening_property=D("0"),
               monthly_contribution=D("40"), monthly_rent=D("0"), goals=(goal,))
    )
    event = result.goal_results[0]
    assert event.funded_amount == D("150.00")
    assert event.shortfall == D("0.00")
    assert result.monthly_points[1].closing_financial == D("30.00")
    assert result.monthly_points[2].closing_financial == D("70.00")

    under = project_family_wealth(replace(_input(monthly_contribution=D("0"), monthly_rent=D("0"), goals=(goal,)), opening_financial=D("100")))
    assert under.goal_results[0].shortfall == D("50.00")
    assert under.monthly_points[1].closing_financial == D("0.00")
    assert under.first_underfunded_goal_key == "too_large"


def test_signed_financial_and_property_growth_allow_safe_negative_rates() -> None:
    result = project_family_wealth(
        _input(opening_financial=D("120000"), opening_property=D("120000"),
               monthly_contribution=D("0"), monthly_rent=D("0"),
               annual_financial_return_pct=D("-12"), property_growth_pct=D("-12"))
    )
    assert result.monthly_points[0].financial_growth < 0
    assert result.monthly_points[0].property_growth < 0


def test_annual_aggregation_uses_last_month_and_sums_flows() -> None:
    result = project_family_wealth(_input(monthly_rent=D("0")))
    assert [p.year for p in result.annual_points] == [2026, 2027]
    assert result.annual_points[0].annual_contributions == D("600000.00")
    assert result.annual_points[1].annual_contributions == D("1200000.00")
    assert result.annual_points[1].on == date(2027, 2, 28)


def test_passive_income_corpus_offset_protection_and_earliest_sustainable_date() -> None:
    passive = _goal(
        "income", "income_target", goal_type="passive_income",
        current_value_amount=D("1200"), target_date=date(2027, 1, 1), priority=1
    )
    later = _goal("later", current_value_amount=D("10000"), target_date=date(2027, 2, 1))
    result = project_family_wealth(
        _input(opening_financial=D("20000"), opening_property=D("0"),
               monthly_contribution=D("0"), monthly_rent=D("100"), rent_growth_pct=D("0"),
               reinvest_rent_until=date(2026, 12, 31), goals=(passive, later,))
    )
    analysis = result.passive_income
    assert analysis is not None
    assert analysis.monthly_gap == D("1100.00")
    assert analysis.required_corpus == D("330000.00")
    assert analysis.later_goals_protected is True
    assert analysis.on_track is False
    assert analysis.earliest_sustainable_date is None
    assert result.goal_results[0].goal_key == "later"


def test_passive_income_reserves_corpus_after_later_goals_and_reports_earliest() -> None:
    passive = _goal(
        "income", "income_target", goal_type="passive_income",
        current_value_amount=D("1200"), target_date=date(2027, 1, 1), priority=1
    )
    later = _goal("later", current_value_amount=D("300000"), target_date=date(2027, 2, 1))
    result = project_family_wealth(
        _input(opening_financial=D("400000"), opening_property=D("0"),
               monthly_contribution=D("0"), monthly_rent=D("100"), rent_growth_pct=D("0"),
               reinvest_rent_until=date(2026, 12, 31), goals=(passive, later,))
    )
    assert result.goal_results[0].shortfall == D("0.00")
    assert result.passive_income.later_goals_protected is True
    assert result.passive_income.on_track is False
    assert result.passive_income.earliest_sustainable_date is None

    sustainable = project_family_wealth(
        replace(_input(opening_financial=D("700000"), opening_property=D("0"),
                       monthly_contribution=D("0"), monthly_rent=D("100"), rent_growth_pct=D("0"),
                       reinvest_rent_until=date(2026, 12, 31), goals=(passive, later,)))
    )
    assert sustainable.passive_income.on_track is True
    assert sustainable.passive_income.later_goals_protected is True
    assert sustainable.passive_income.earliest_sustainable_date == date(2027, 1, 31)


def test_scenario_returns_produce_separate_outputs() -> None:
    low = project_family_wealth(_input(annual_financial_return_pct=D("0")))
    high = project_family_wealth(_input(annual_financial_return_pct=D("12")))
    assert high.ending_financial > low.ending_financial


@pytest.mark.parametrize(
    "changes",
    [
        {"calculated_on": date(2027, 1, 1), "end_date": date(2026, 12, 31)},
        {"calculated_on": date(2020, 1, 1), "end_date": date(2070, 2, 1)},
        {"annual_financial_return_pct": D("NaN")},
        {"property_growth_pct": D("Infinity")},
        {"annual_financial_return_pct": D("-100")},
    ],
)
def test_unsafe_inputs_are_rejected(changes) -> None:
    with pytest.raises(UnsafeProjection):
        project_family_wealth(_input(**changes))


@pytest.mark.parametrize(
    "goals",
    [
        (_goal("negative", current_value_amount=D("-1")),),
        (_goal("duplicate"), _goal("duplicate", target_date=date(2027, 2, 1))),
        (_goal("outside", target_date=date(2028, 1, 1)),),
    ],
)
def test_unsafe_goal_configuration_is_rejected(goals) -> None:
    with pytest.raises(UnsafeProjection):
        project_family_wealth(_input(goals=goals))


def test_large_values_remain_finite_decimal_cents_and_models_are_frozen() -> None:
    result = project_family_wealth(
        _input(opening_financial=D("999999999999999"),
               opening_property=D("999999999999999"), monthly_contribution=D("0"))
    )
    assert result.ending_total.is_finite()
    assert result.ending_total.as_tuple().exponent == -2
    assert math.isfinite(float(result.ending_total))
    with pytest.raises(FrozenInstanceError):
        result.ending_total = D("0")
