from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, computed_field, model_validator


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


class GoalSettings(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    target_amount_inr: float = Field(gt=0)
    deadline: date


class GoalScenarioSettings(BaseModel):
    scenario_key: ScenarioKey
    annual_return_pct: float = Field(ge=-25, le=50)
    monthly_contribution_inr: float = Field(ge=0)


class GoalConfigurationUpdate(BaseModel):
    goal: GoalSettings
    scenarios: list[GoalScenarioSettings]

    @model_validator(mode="after")
    def validate_scenarios(self):
        keys = [scenario.scenario_key for scenario in self.scenarios]
        expected_keys = ["conservative", "expected", "optimistic"]
        if keys != expected_keys:
            raise ValueError(
                "scenarios must be conservative, expected, optimistic in that order"
            )
        rates = [scenario.annual_return_pct for scenario in self.scenarios]
        if rates != sorted(rates):
            raise ValueError(
                "scenario returns must satisfy conservative <= expected <= optimistic"
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
