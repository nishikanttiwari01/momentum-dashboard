"""Pure calculations for projecting a wealth goal."""

from dataclasses import dataclass
from datetime import date
import calendar
import math
from numbers import Integral, Real


@dataclass(frozen=True)
class TrajectoryPoint:
    on: date
    balance: float


def _finite_number(value: Real, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def _positive_months(months: int) -> int:
    if isinstance(months, bool) or not isinstance(months, Integral) or months <= 0:
        raise ValueError("months must be a positive integer")
    return int(months)


def _projection_inputs(start, annual_return_pct, monthly):
    start = _finite_number(start, "start")
    annual_return_pct = _finite_number(annual_return_pct, "annual_return_pct")
    monthly = _finite_number(monthly, "monthly")
    if monthly < 0:
        raise ValueError("monthly must not be negative")
    if annual_return_pct <= -1200:
        raise ValueError("annual return must imply a monthly rate above -100%")
    return start, annual_return_pct, monthly


def project_balance(start, annual_return_pct, monthly, months):
    """Project a balance using contributions made at each month's end."""
    start, annual_return_pct, monthly = _projection_inputs(
        start, annual_return_pct, monthly
    )
    months = _positive_months(months)
    rate = annual_return_pct / 1200
    if rate == 0:
        return start + monthly * months
    growth = (1 + rate) ** months
    return start * growth + monthly * ((growth - 1) / rate)


def required_monthly_contribution(start, target, months, annual_return_pct):
    """Return the non-negative monthly amount needed to reach ``target``."""
    start = _finite_number(start, "start")
    target = _finite_number(target, "target")
    annual_return_pct = _finite_number(annual_return_pct, "annual_return_pct")
    months = _positive_months(months)
    if annual_return_pct <= -1200:
        raise ValueError("annual return must imply a monthly rate above -100%")

    rate = annual_return_pct / 1200
    growth = (1 + rate) ** months
    shortfall = target - start * growth
    if shortfall <= 0:
        return 0.0
    if rate == 0:
        return shortfall / months
    annuity_factor = (growth - 1) / rate
    return max(0.0, shortfall / annuity_factor)


def whole_months_between(calculated_on, deadline):
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


def monthly_trajectory(calculated_on, start, annual_return_pct, monthly, months):
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
    calculated_on, start, target, annual_return_pct, monthly
):
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
