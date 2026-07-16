from __future__ import annotations

import math
from datetime import date, datetime
from typing import Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    computed_field,
    model_validator,
)
from pydantic_core import PydanticCustomError


IGNORED_SHEETS = frozenset({"MF discont.", "Property Cal.", "REMIT", "STOCKS RECMDN"})


class ImportIssue(BaseModel):
    severity: Literal["warning", "error"]
    code: str
    message: str
    sheet: str | None = None
    row: int | None = Field(None, ge=1)

    @model_validator(mode="after")
    def protect_ignored_sheets(self):
        if self.sheet in IGNORED_SHEETS:
            raise ValueError("ignored sheet details cannot be exposed")
        return self


class ImportPreview(BaseModel):
    preview_token: str
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    recognized_sheets: list[str]
    ignored_sheets: list[str]
    counts: dict[str, int]
    issues: list[ImportIssue]

    @computed_field
    @property
    def blocking_error_count(self) -> int:
        return sum(issue.severity == "error" for issue in self.issues)


class ImportCommitResult(BaseModel):
    snapshot_id: str
    created: bool


class SnapshotSummary(BaseModel):
    snapshot_id: str
    as_of: date
    created_at: datetime
    source_filename: str


class FxMetadata(BaseModel):
    pair: str = "USD/INR"
    rate: float = Field(gt=0)
    effective_on: date
    fetched_at: datetime
    source: str
    is_fallback: bool = False


class MarketExposure(BaseModel):
    market: str
    market_value_inr: float
    weight_pct: float


class WealthSummary(BaseModel):
    snapshot_id: str | None = None
    as_of: date | None = None
    net_worth_market_value_inr: float | None = None
    invested_capital_inr: float | None = None
    investment_xirr_pct: float | None = None
    market_exposure: list[MarketExposure] = Field(default_factory=list)
    fx: FxMetadata | None = None
    data_health: Literal["empty", "fresh", "warning", "unavailable"] = "empty"


ScenarioKey = Literal["conservative", "expected", "optimistic"]
GoalType = Literal["education", "house", "marriage", "passive_income"]
FundingTreatment = Literal["expense", "asset_conversion", "income_target"]


class GoalSettings(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    name: str = Field(min_length=1, max_length=120)
    target_amount_inr: float = Field(gt=0, le=1_000_000_000_000_000)
    deadline: date


class GoalScenarioSettings(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    scenario_key: ScenarioKey
    annual_return_pct: float = Field(ge=-25, le=50)
    monthly_contribution_inr: float = Field(ge=0, le=1_000_000_000_000)


class GoalConfigurationUpdate(BaseModel):
    goal: GoalSettings
    scenarios: list[GoalScenarioSettings]

    @model_validator(mode="after")
    def validate_scenarios(self):
        keys = [scenario.scenario_key for scenario in self.scenarios]
        expected_keys = ["conservative", "expected", "optimistic"]
        if keys != expected_keys:
            message = (
                "scenarios must be conservative, expected, optimistic in that order"
            )
            mismatch = next(
                (
                    index
                    for index, (actual, expected) in enumerate(zip(keys, expected_keys))
                    if actual != expected
                ),
                None,
            )
            loc = (
                ("scenarios", mismatch, "scenario_key")
                if mismatch is not None
                else ("scenarios",)
            )
            raise ValidationError.from_exception_data(
                self.__class__.__name__,
                [
                    {
                        "type": PydanticCustomError("scenario_key_order", message),
                        "loc": loc,
                        "input": keys,
                    }
                ],
            )
        rates = [scenario.annual_return_pct for scenario in self.scenarios]
        for index in range(1, len(rates)):
            if rates[index - 1] <= rates[index]:
                continue
            message = (
                "scenario returns must satisfy "
                "conservative <= expected <= optimistic"
            )
            raise ValidationError.from_exception_data(
                self.__class__.__name__,
                [
                    {
                        "type": PydanticCustomError("scenario_return_order", message),
                        "loc": ("scenarios", index, "annual_return_pct"),
                        "input": rates[index],
                    }
                ],
            )
        return self


class GoalTrajectoryPoint(BaseModel):
    on: date
    balance_inr: float


class GoalScenarioProjection(BaseModel):
    settings: GoalScenarioSettings
    projected_deadline_value_inr: float | None = None
    surplus_or_shortfall_inr: float | None = None
    on_track: bool | None = None
    projected_completion_date: date | None = None
    trajectory: list[GoalTrajectoryPoint] = Field(default_factory=list)


class PrimaryGoalResponse(BaseModel):
    goal: GoalSettings
    scenario_projections: list[GoalScenarioProjection]
    calculated_on: date
    snapshot_id: str | None = None
    current_value_inr: float | None = None
    achieved_pct: float | None = None
    remaining_inr: float | None = None
    required_monthly_contribution_inr: float | None = None
    required_trajectory: list[GoalTrajectoryPoint] = Field(default_factory=list)
    data_health: Literal["empty", "fresh", "warning", "unavailable"] = "empty"


class FamilyPlanAssumptions(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    monthly_contribution_inr: float = Field(ge=0, le=1_000_000_000_000)
    contribution_step_up_enabled: bool
    contribution_step_up_pct: float = Field(ge=0, le=25)
    monthly_rent_inr: float = Field(ge=0, le=1_000_000_000)
    rent_growth_pct: float = Field(ge=-25, le=50)
    reinvest_rent_until: date
    property_growth_pct: float = Field(ge=-25, le=50)
    withdrawal_rate_pct: float = Field(gt=0, le=20)
    amber_margin_pct: float = Field(ge=0, le=100)


class LinkedGoalSettings(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    goal_key: str = Field(pattern=r"^[a-z0-9_]+$", max_length=40)
    name: str = Field(min_length=1, max_length=120)
    goal_type: GoalType
    current_value_amount_inr: float = Field(gt=0, le=1_000_000_000_000_000)
    target_date: date
    inflation_pct: float = Field(ge=0, le=25)
    funding_treatment: FundingTreatment
    priority: int = Field(ge=1, le=100)
    enabled: bool
    display_order: int = Field(ge=0, le=100)


class FamilyScenarioSettings(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    scenario_key: ScenarioKey
    financial_return_pct: float = Field(
        ge=-25, le=50,
        validation_alias=AliasChoices("financial_return_pct", "annual_return_pct"),
    )
    property_growth_pct: float = Field(default=6, ge=-25, le=30)
    monthly_contribution_inr: float = Field(
        default=600_000, ge=0, le=1_000_000_000_000
    )
    step_up_enabled: bool = False
    step_up_pct: float = Field(default=6, ge=0, le=25)
    contribution_stop_age: int = Field(default=60, ge=18, le=120)

    @property
    def annual_return_pct(self) -> float:
        """Compatibility accessor for staged service migration."""
        return self.financial_return_pct


def _contract_error(
    model_title: str, error_type: str, message: str, loc: tuple, value
):
    return ValidationError.from_exception_data(
        model_title,
        [
            {
                "type": PydanticCustomError(error_type, message),
                "loc": loc,
                "input": value,
            }
        ],
    )


def _validate_ordered_scenarios(
    model_title: str,
    keys: list[ScenarioKey],
    rates: list[float],
    root: str,
    key_path: tuple[str, ...] = (),
) -> None:
    expected_keys: list[ScenarioKey] = ["conservative", "expected", "optimistic"]
    if keys != expected_keys:
        mismatch = next(
            (
                index
                for index, expected in enumerate(expected_keys)
                if index >= len(keys) or keys[index] != expected
            ),
            None,
        )
        location = (
            (root, mismatch, *key_path, "scenario_key")
            if mismatch is not None and mismatch < len(keys)
            else (root,)
        )
        raise _contract_error(
            model_title,
            "scenario_key_order",
            "scenarios must be conservative, expected, optimistic in that order",
            location,
            keys,
        )
    for index in range(1, len(rates)):
        if rates[index - 1] > rates[index]:
            raise _contract_error(
                model_title,
                "scenario_return_order",
                "scenario returns must satisfy conservative <= expected <= optimistic",
                (root, index, *key_path, "financial_return_pct"),
                rates[index],
            )


class FamilyPlanUpdate(BaseModel):
    birth_year: int = Field(default=1984, ge=1900, le=date.today().year)
    birth_month: int = Field(default=7, ge=1, le=12)
    projection_end_age: int = Field(default=80, ge=18, le=120)
    primary_goal: GoalSettings | None = None
    assumptions: FamilyPlanAssumptions
    scenarios: list[FamilyScenarioSettings]
    goals: list[LinkedGoalSettings]

    @model_validator(mode="after")
    def validate_plan_contract(self):
        keys = [scenario.scenario_key for scenario in self.scenarios]
        rates = [scenario.financial_return_pct for scenario in self.scenarios]
        _validate_ordered_scenarios(
            "FamilyPlanUpdate", keys, rates, "scenarios"
        )

        today = date.today()
        current_age = today.year - self.birth_year - (
            (today.month, today.day) < (self.birth_month, 1)
        )
        if self.projection_end_age < current_age:
            raise _contract_error(
                "FamilyPlanUpdate", "projection_horizon_past",
                "projection_end_age cannot be below current age",
                ("projection_end_age",), self.projection_end_age,
            )
        for index, scenario in enumerate(self.scenarios):
            if scenario.contribution_stop_age < current_age:
                raise _contract_error(
                    "FamilyPlanUpdate", "contribution_stop_age_past",
                    "contribution_stop_age cannot be below current age",
                    ("scenarios", index, "contribution_stop_age"),
                    scenario.contribution_stop_age,
                )
            if scenario.contribution_stop_age > self.projection_end_age:
                raise _contract_error(
                    "FamilyPlanUpdate", "contribution_stop_after_horizon",
                    "contribution_stop_age cannot exceed projection_end_age",
                    ("scenarios", index, "contribution_stop_age"),
                    scenario.contribution_stop_age,
                )

        goal_keys = [goal.goal_key for goal in self.goals]
        if len(goal_keys) != len(set(goal_keys)):
            raise _contract_error(
                "FamilyPlanUpdate",
                "duplicate_goal_key",
                "goal_key values must be unique",
                ("goals",),
                goal_keys,
            )

        expected_treatments: dict[GoalType, FundingTreatment] = {
            "education": "expense",
            "house": "asset_conversion",
            "marriage": "expense",
            "passive_income": "income_target",
        }
        for index, goal in enumerate(self.goals):
            expected = expected_treatments[goal.goal_type]
            if goal.funding_treatment != expected:
                raise _contract_error(
                    "FamilyPlanUpdate",
                    "funding_treatment_mismatch",
                    f"{goal.goal_type} goals require {expected} funding treatment",
                    ("goals", index, "funding_treatment"),
                    goal.funding_treatment,
                )
        return self

    def validate_target_dates(self, reference_date: date) -> FamilyPlanUpdate:
        for index, goal in enumerate(self.goals):
            if goal.enabled and goal.target_date <= reference_date:
                raise _contract_error(
                    "FamilyPlanUpdate",
                    "target_date_not_future",
                    "enabled goals require a future target_date",
                    ("goals", index, "target_date"),
                    goal.target_date,
                )
        return self


def _money_isclose(left: float, right: float) -> bool:
    ulp_tolerance = 4 * max(math.ulp(left), math.ulp(right))
    return math.isclose(
        left,
        right,
        rel_tol=0,
        abs_tol=max(0.01, ulp_tolerance),
    )


class AnnualRunwayEvent(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    goal_key: str
    goal_name: str
    goal_type: GoalType
    funding_treatment: FundingTreatment
    amount_inr: float = Field(ge=0)
    funded_amount_inr: float = Field(ge=0)
    shortfall_inr: float = Field(ge=0)

    @model_validator(mode="after")
    def validate_funding_total(self):
        if not _money_isclose(
            self.funded_amount_inr + self.shortfall_inr, self.amount_inr
        ):
            raise ValueError("funded amount plus shortfall must equal event amount")
        return self


class AnnualRunwayPoint(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    on: date
    age: int | None = Field(default=None, ge=0, le=150)
    financial_assets_inr: float = Field(ge=0)
    property_value_inr: float = Field(ge=0)
    total_net_worth_inr: float = Field(ge=0)
    annual_contributions_inr: float = Field(ge=0)
    annual_rent_inr: float = Field(ge=0)
    rent_received_inr: float = Field(default=0, ge=0)
    rent_reinvested_inr: float = Field(default=0, ge=0)
    financial_growth_inr: float
    property_growth_inr: float
    goal_outflows_inr: float = Field(ge=0)
    events: list[AnnualRunwayEvent] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_net_worth_total(self):
        if not _money_isclose(
            self.financial_assets_inr + self.property_value_inr,
            self.total_net_worth_inr,
        ):
            raise ValueError("total net worth must equal financial assets plus property")
        return self


class GoalHealth(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    goal: LinkedGoalSettings
    inflated_cost_inr: float = Field(ge=0)
    available_before_inr: float = Field(ge=0)
    funded_amount_inr: float = Field(ge=0)
    shortfall_inr: float = Field(ge=0)
    funded_pct: float = Field(ge=0, le=100)
    status: Literal["green", "amber", "red"]
    reason: str

    @model_validator(mode="after")
    def validate_funding_total(self):
        if not _money_isclose(
            self.funded_amount_inr + self.shortfall_inr, self.inflated_cost_inr
        ):
            raise ValueError("funded amount plus shortfall must equal inflated cost")
        return self


class PassiveIncomeAnalysis(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    target_date: date
    target_monthly_income_inr: float = Field(ge=0)
    projected_monthly_rent_inr: float = Field(ge=0)
    portfolio_monthly_gap_inr: float = Field(ge=0)
    required_corpus_inr: float = Field(ge=0)
    supported_portfolio_monthly_income_inr: float = Field(ge=0)
    total_monthly_income_inr: float = Field(ge=0)
    surplus_or_shortfall_inr: float
    on_track: bool
    later_goals_protected: bool
    earliest_sustainable_date: date | None = None


class December2029Milestone(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    target_date: date
    target_amount_inr: float = Field(gt=0)
    projected_value_inr: float = Field(ge=0)
    surplus_or_shortfall_inr: float
    on_track: bool


class FamilyScenarioProjection(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    settings: FamilyScenarioSettings
    annual_points: list[AnnualRunwayPoint]
    goal_health: list[GoalHealth]
    passive_income: PassiveIncomeAnalysis | None = None
    ending_financial_assets_inr: float = Field(ge=0)
    ending_property_value_inr: float = Field(ge=0)
    ending_total_net_worth_inr: float = Field(ge=0)
    first_underfunded_goal_key: str | None = None
    december_2029_milestone: December2029Milestone | None = None

    @model_validator(mode="after")
    def validate_ending_net_worth_total(self):
        if not _money_isclose(
            self.ending_financial_assets_inr + self.ending_property_value_inr,
            self.ending_total_net_worth_inr,
        ):
            raise ValueError(
                "ending total net worth must equal ending financial assets plus property"
            )
        return self


class FamilyPlanResponse(BaseModel):
    birth_year: int = Field(default=1984, ge=1900, le=date.today().year)
    birth_month: int = Field(default=7, ge=1, le=12)
    projection_end_age: int = Field(default=80, ge=18, le=120)
    primary_goal: PrimaryGoalResponse
    calculated_on: date
    snapshot_id: str | None = None
    data_health: Literal["empty", "fresh", "warning", "unavailable"] = "empty"
    assumptions: FamilyPlanAssumptions
    goals: list[LinkedGoalSettings]
    scenario_projections: list[FamilyScenarioProjection]

    @model_validator(mode="after")
    def validate_response_contract(self):
        keys = [item.settings.scenario_key for item in self.scenario_projections]
        rates = [item.settings.financial_return_pct for item in self.scenario_projections]
        _validate_ordered_scenarios(
            "FamilyPlanResponse",
            keys,
            rates,
            "scenario_projections",
            key_path=("settings",),
        )
        goal_keys = [goal.goal_key for goal in self.goals]
        if len(goal_keys) != len(set(goal_keys)):
            raise _contract_error(
                "FamilyPlanResponse",
                "duplicate_goal_key",
                "goal_key values must be unique",
                ("goals",),
                goal_keys,
            )
        return self
