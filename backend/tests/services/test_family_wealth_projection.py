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


def test_flat_contribution_and_step_up_after_full_plan_year() -> None:
    flat = project_family_wealth(_input())
    stepped = project_family_wealth(
        _input(calculated_on=date(2026, 1, 1), end_date=date(2027, 1, 31),
               contribution_step_up_enabled=True)
    )

    assert [p.contribution for p in flat.monthly_points] == [D("600000.00")] * 3
    assert stepped.monthly_points[0].contribution == D("600000.00")
    assert stepped.monthly_points[-1].on == date(2027, 1, 31)
    assert stepped.monthly_points[-1].contribution == D("636000.00")


def test_december_plan_does_not_step_until_second_january() -> None:
    result = project_family_wealth(
        _input(end_date=date(2028, 1, 31), contribution_step_up_enabled=True)
    )
    january_points = [p for p in result.monthly_points if p.on.month == 1]
    assert [(p.on.year, p.contribution) for p in january_points] == [
        (2027, D("600000.00")), (2028, D("636000.00"))
    ]


@pytest.mark.parametrize("start_month", [2, 7, 12])
def test_rent_uses_calendar_year_but_contribution_waits_for_plan_year(
    start_month: int,
) -> None:
    result = project_family_wealth(
        _input(calculated_on=date(2026, start_month, 15), end_date=date(2028, 1, 31),
               contribution_step_up_enabled=True, monthly_rent=D("100"))
    )
    january = {p.on.year: p for p in result.monthly_points if p.on.month == 1}
    assert january[2027].projected_monthly_rent == D("110.00")
    assert january[2027].contribution == D("600000.00")
    assert january[2028].projected_monthly_rent == D("121.00")
    assert january[2028].contribution == D("636000.00")


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


def test_partial_calculation_month_is_full_bucket_and_midmonth_goal_runs_at_end() -> None:
    goal = _goal("midmonth", target_date=date(2026, 7, 20), current_value_amount=D("50"))
    result = project_family_wealth(
        _input(calculated_on=date(2026, 7, 15), end_date=date(2026, 7, 31),
               opening_financial=D("100"), opening_property=D("0"),
               monthly_contribution=D("40"), monthly_rent=D("0"), goals=(goal,))
    )
    assert len(result.monthly_points) == 1
    point = result.monthly_points[0]
    assert point.on == date(2026, 7, 31)
    assert point.contribution == D("40.00")
    assert point.events[0].goal_key == "midmonth"
    assert point.closing_financial == D("90.00")


def test_underfunded_event_floors_at_zero_and_later_inflows_rebuild() -> None:
    goal = _goal("too_large", current_value_amount=D("250"))
    under = project_family_wealth(
        _input(opening_financial=D("100"), opening_property=D("0"),
               monthly_contribution=D("40"), monthly_rent=D("0"), goals=(goal,))
    )
    assert under.goal_results[0].funded_amount == D("180.00")
    assert under.goal_results[0].shortfall == D("70.00")
    assert under.monthly_points[1].closing_financial == D("0.00")
    assert under.monthly_points[2].closing_financial == D("40.00")
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
    goal = _goal("annual_event", current_value_amount=D("100000"))
    result = project_family_wealth(
        _input(annual_financial_return_pct=D("12"), property_growth_pct=D("6"),
               goals=(goal,))
    )
    assert [p.year for p in result.annual_points] == [2026, 2027]
    assert result.annual_points[0].annual_contributions == D("600000.00")
    assert result.annual_points[1].annual_contributions == D("1200000.00")
    assert result.annual_points[1].on == date(2027, 2, 28)
    points_2027 = [p for p in result.monthly_points if p.on.year == 2027]
    annual = result.annual_points[1]
    assert annual.annual_reinvested_rent == sum(p.reinvested_rent for p in points_2027)
    assert annual.annual_financial_growth == sum(p.financial_growth for p in points_2027)
    assert annual.annual_property_growth == sum(p.property_growth for p in points_2027)
    assert annual.annual_goal_outflows == D("100000.00")
    assert [event.goal_key for event in annual.events] == ["annual_event"]


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
    assert analysis.later_goals_protected is False
    assert analysis.on_track is False
    assert analysis.earliest_sustainable_date is None
    assert analysis.supported_portfolio_monthly_income == D("67.00")
    assert analysis.total_supported_monthly_income == D("167.00")
    assert analysis.surplus_or_shortfall == D("-309900.00")
    assert result.goal_results[0].goal_key == "later"


def test_later_goal_is_unprotected_when_its_spend_invades_passive_corpus() -> None:
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
    assert result.passive_income.later_goals_protected is False
    assert result.passive_income.on_track is False
    assert result.passive_income.earliest_sustainable_date is None


def test_later_contributions_fund_goal_while_preserving_passive_corpus() -> None:
    passive = _goal(
        "income", "income_target", goal_type="passive_income",
        current_value_amount=D("1200"), target_date=date(2027, 1, 1), priority=1
    )
    later = _goal("later", current_value_amount=D("200000"), target_date=date(2027, 2, 1))
    sustainable = project_family_wealth(
        _input(opening_financial=D("100000"), opening_property=D("0"),
               monthly_contribution=D("150000"), monthly_rent=D("100"), rent_growth_pct=D("0"),
               reinvest_rent_until=date(2026, 11, 30), goals=(passive, later,))
    )
    assert sustainable.passive_income.on_track is True
    assert sustainable.passive_income.later_goals_protected is True
    assert sustainable.passive_income.earliest_sustainable_date == date(2027, 1, 31)
    assert sustainable.passive_income.surplus_or_shortfall == D("70000.00")


def test_scenario_returns_produce_separate_outputs() -> None:
    low = project_family_wealth(_input(annual_financial_return_pct=D("0")))
    high = project_family_wealth(_input(annual_financial_return_pct=D("12")))
    assert high.ending_financial > low.ending_financial


def test_int_float_and_string_numerics_are_normalized_to_decimal_equivalently() -> None:
    decimal_result = project_family_wealth(_input())
    mixed = replace(
        _input(), opening_financial=1_000_000, opening_property=2_000_000.0,
        monthly_contribution="600000", contribution_step_up_pct=6.0,
        monthly_rent="10000", rent_growth_pct=10, property_growth_pct="0",
        withdrawal_rate_pct=4.0, amber_margin_pct="10",
        annual_financial_return_pct=0,
        goals=(replace(_goal("disabled"), enabled=False,
                       current_value_amount="100", inflation_pct=0.0),),
    )
    mixed_result = project_family_wealth(mixed)
    assert mixed_result.monthly_points == decimal_result.monthly_points
    assert isinstance(mixed_result.ending_financial, Decimal)


@pytest.mark.parametrize("bad", ["junk", float("nan"), float("inf"), object()])
def test_invalid_numeric_types_always_raise_unsafe_projection(bad) -> None:
    with pytest.raises(UnsafeProjection):
        project_family_wealth(replace(_input(), monthly_contribution=bad))


@pytest.mark.parametrize(
    "goal",
    [
        _goal("bad_treatment", treatment="transfer"),
        _goal("bad_type", goal_type="retirement"),
        _goal("house_expense", goal_type="house", treatment="expense"),
        _goal("income_expense", goal_type="passive_income", treatment="expense"),
        _goal("education_asset", goal_type="education", treatment="asset_conversion"),
        _goal("marriage_income", goal_type="marriage", treatment="income_target"),
    ],
)
def test_unknown_or_mismatched_goal_type_and_treatment_are_rejected(goal) -> None:
    with pytest.raises(UnsafeProjection):
        project_family_wealth(_input(goals=(goal,)))


def test_more_than_one_enabled_income_target_is_rejected() -> None:
    goals = (
        _goal("income_a", goal_type="passive_income", treatment="income_target"),
        _goal("income_b", goal_type="passive_income", treatment="income_target"),
    )
    with pytest.raises(UnsafeProjection):
        project_family_wealth(_input(goals=goals))


@pytest.mark.parametrize(
    "available,status",
    [(D("99"), "red"), (D("119.99"), "amber"), (D("120"), "green")],
)
def test_goal_health_uses_configured_available_before_margin(available, status) -> None:
    goal = _goal("health", current_value_amount=D("100"))
    result = project_family_wealth(
        _input(opening_financial=available, opening_property=D("0"),
               monthly_contribution=D("0"), monthly_rent=D("0"),
               amber_margin_pct=D("20"), goals=(goal,))
    )
    health = result.goal_results[0]
    assert health.health_status == status
    assert health.health_reason


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


def test_enabled_goal_before_calculation_date_is_rejected() -> None:
    with pytest.raises(UnsafeProjection):
        project_family_wealth(
            _input(goals=(_goal("past", target_date=date(2026, 11, 30)),))
        )


def test_large_values_remain_finite_decimal_cents_and_models_are_frozen() -> None:
    result = project_family_wealth(
        _input(opening_financial=D("999999999999999"),
               opening_property=D("999999999999999"), monthly_contribution=D("0"),
               annual_financial_return_pct=D("12"), property_growth_pct=D("6"))
    )
    for value in (result.ending_financial, result.ending_property, result.ending_total):
        assert value.is_finite()
        assert value.as_tuple().exponent == -2
        assert math.isfinite(float(value))
    with pytest.raises(FrozenInstanceError):
        result.ending_total = D("0")
