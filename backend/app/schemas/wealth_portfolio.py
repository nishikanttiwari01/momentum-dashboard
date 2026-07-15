from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import (
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
    annual_return_pct: float = Field(ge=-25, le=50)


def _contract_error(error_type: str, message: str, loc: tuple, value):
    return ValidationError.from_exception_data(
        "FamilyPlanUpdate",
        [
            {
                "type": PydanticCustomError(error_type, message),
                "loc": loc,
                "input": value,
            }
        ],
    )


class FamilyPlanUpdate(BaseModel):
    assumptions: FamilyPlanAssumptions
    scenarios: list[FamilyScenarioSettings]
    goals: list[LinkedGoalSettings]

    @model_validator(mode="after")
    def validate_plan_contract(self):
        expected_keys = ["conservative", "expected", "optimistic"]
        keys = [scenario.scenario_key for scenario in self.scenarios]
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
                ("scenarios", mismatch, "scenario_key")
                if mismatch is not None and mismatch < len(keys)
                else ("scenarios",)
            )
            raise _contract_error(
                "scenario_key_order",
                "scenarios must be conservative, expected, optimistic in that order",
                location,
                keys,
            )

        rates = [scenario.annual_return_pct for scenario in self.scenarios]
        for index in range(1, len(rates)):
            if rates[index - 1] > rates[index]:
                raise _contract_error(
                    "scenario_return_order",
                    "scenario returns must satisfy conservative <= expected <= optimistic",
                    ("scenarios", index, "annual_return_pct"),
                    rates[index],
                )

        goal_keys = [goal.goal_key for goal in self.goals]
        if len(goal_keys) != len(set(goal_keys)):
            raise _contract_error(
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
                    "funding_treatment_mismatch",
                    f"{goal.goal_type} goals require {expected} funding treatment",
                    ("goals", index, "funding_treatment"),
                    goal.funding_treatment,
                )
        return self


class AnnualRunwayEvent(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    goal_key: str
    goal_name: str
    goal_type: GoalType
    funding_treatment: FundingTreatment
    amount_inr: float
    funded_amount_inr: float
    shortfall_inr: float


class AnnualRunwayPoint(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    on: date
    financial_assets_inr: float
    property_value_inr: float
    total_net_worth_inr: float
    annual_contributions_inr: float
    annual_rent_inr: float
    financial_growth_inr: float
    property_growth_inr: float
    goal_outflows_inr: float
    events: list[AnnualRunwayEvent] = Field(default_factory=list)


class GoalHealth(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    goal: LinkedGoalSettings
    inflated_cost_inr: float
    available_before_inr: float
    funded_amount_inr: float
    shortfall_inr: float
    funded_pct: float
    status: Literal["green", "amber", "red"]
    reason: str


class PassiveIncomeAnalysis(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    target_date: date
    target_monthly_income_inr: float
    projected_monthly_rent_inr: float
    portfolio_monthly_gap_inr: float
    required_corpus_inr: float
    supported_portfolio_monthly_income_inr: float
    total_monthly_income_inr: float
    surplus_or_shortfall_inr: float
    on_track: bool
    later_goals_protected: bool
    earliest_sustainable_date: date | None = None


class FamilyScenarioProjection(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    settings: FamilyScenarioSettings
    annual_points: list[AnnualRunwayPoint]
    goal_health: list[GoalHealth]
    passive_income: PassiveIncomeAnalysis | None = None
    ending_financial_assets_inr: float
    ending_property_value_inr: float
    ending_total_net_worth_inr: float
    first_underfunded_goal_key: str | None = None


class FamilyPlanResponse(BaseModel):
    primary_goal: PrimaryGoalResponse
    calculated_on: date
    snapshot_id: str | None = None
    data_health: Literal["empty", "fresh", "warning", "unavailable"] = "empty"
    assumptions: FamilyPlanAssumptions
    goals: list[LinkedGoalSettings]
    scenario_projections: list[FamilyScenarioProjection]
