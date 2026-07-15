export type ImportIssue = {
  severity: 'warning' | 'error';
  code: string;
  message: string;
  sheet?: string | null;
  row?: number | null;
};

export type ImportPreview = {
  preview_token: string;
  source_sha256: string;
  recognized_sheets: string[];
  ignored_sheets: string[];
  counts: Record<string, number>;
  issues: ImportIssue[];
  blocking_error_count: number;
};

export type ImportCommitResult = { snapshot_id: string; created: boolean };

export type FxMetadata = {
  pair: string;
  rate: number;
  effective_on: string;
  fetched_at: string;
  source: string;
  is_fallback: boolean;
};

export type WealthSummary = {
  snapshot_id: string | null;
  as_of: string | null;
  net_worth_market_value_inr: number | null;
  invested_capital_inr: number | null;
  investment_xirr_pct: number | null;
  market_exposure: { market: string; market_value_inr: number; weight_pct: number }[];
  fx: FxMetadata | null;
  data_health: 'empty' | 'fresh' | 'warning' | 'unavailable';
};

export type WealthDataHealth = 'empty' | 'fresh' | 'warning' | 'unavailable';

export type GoalSettings = {
  name: string;
  target_amount_inr: number;
  deadline: string;
};

export type GoalScenarioKey = 'conservative' | 'expected' | 'optimistic';

export type GoalScenarioSettings = {
  scenario_key: GoalScenarioKey;
  annual_return_pct: number;
  monthly_contribution_inr: number;
};

export type GoalScenarioUpdate = GoalScenarioSettings;

export type GoalConfigurationUpdate = {
  goal: GoalSettings;
  scenarios: GoalScenarioUpdate[];
};

export type GoalTrajectoryPoint = {
  on: string;
  balance_inr: number;
};

export type GoalScenarioProjection = {
  settings: GoalScenarioSettings;
  projected_deadline_value_inr: number | null;
  surplus_or_shortfall_inr: number | null;
  on_track: boolean | null;
  projected_completion_date: string | null;
  trajectory: GoalTrajectoryPoint[];
};

export type PrimaryGoalResponse = {
  goal: GoalSettings;
  scenario_projections: GoalScenarioProjection[];
  calculated_on: string;
  snapshot_id: string | null;
  current_value_inr: number | null;
  achieved_pct: number | null;
  remaining_inr: number | null;
  required_monthly_contribution_inr: number | null;
  required_trajectory: GoalTrajectoryPoint[];
  data_health: WealthDataHealth;
};

export type ProblemLocationPart = string | number;

export type FieldProblemError = {
  loc: ProblemLocationPart[];
  msg: string;
  type: string;
  input?: unknown;
};

export type FieldProblemResponse = {
  errors: FieldProblemError[];
};

export type FamilyGoalType = 'education' | 'house' | 'marriage' | 'passive_income';
export type FamilyFundingTreatment = 'expense' | 'asset_conversion' | 'income_target';
export type FamilyScenarioKey = 'conservative' | 'expected' | 'optimistic';
export type FamilyGoalHealthStatus = 'green' | 'amber' | 'red';

export type FamilyPlanAssumptions = {
  monthly_contribution_inr: number;
  contribution_step_up_enabled: boolean;
  contribution_step_up_pct: number;
  monthly_rent_inr: number;
  rent_growth_pct: number;
  reinvest_rent_until: string;
  property_growth_pct: number;
  withdrawal_rate_pct: number;
  amber_margin_pct: number;
};

export type LinkedGoalSettings = {
  goal_key: string;
  name: string;
  goal_type: FamilyGoalType;
  current_value_amount_inr: number;
  target_date: string;
  inflation_pct: number;
  funding_treatment: FamilyFundingTreatment;
  priority: number;
  enabled: boolean;
  display_order: number;
};

export type FamilyScenarioSettings = {
  scenario_key: FamilyScenarioKey;
  annual_return_pct: number;
};

export type AnnualRunwayEvent = {
  goal_key: string;
  goal_name: string;
  goal_type: FamilyGoalType;
  funding_treatment: FamilyFundingTreatment;
  amount_inr: number;
  funded_amount_inr: number;
  shortfall_inr: number;
};

export type AnnualRunwayPoint = {
  on: string;
  financial_assets_inr: number;
  property_value_inr: number;
  total_net_worth_inr: number;
  annual_contributions_inr: number;
  annual_rent_inr: number;
  financial_growth_inr: number;
  property_growth_inr: number;
  goal_outflows_inr: number;
  events: AnnualRunwayEvent[];
};

export type GoalHealth = {
  goal: LinkedGoalSettings;
  inflated_cost_inr: number;
  available_before_inr: number;
  funded_amount_inr: number;
  shortfall_inr: number;
  funded_pct: number;
  status: FamilyGoalHealthStatus;
  reason: string;
};

export type PassiveIncomeAnalysis = {
  target_date: string;
  target_monthly_income_inr: number;
  projected_monthly_rent_inr: number;
  portfolio_monthly_gap_inr: number;
  required_corpus_inr: number;
  supported_portfolio_monthly_income_inr: number;
  total_monthly_income_inr: number;
  surplus_or_shortfall_inr: number;
  on_track: boolean;
  later_goals_protected: boolean;
  earliest_sustainable_date: string | null;
};

export type FamilyScenarioProjection = {
  settings: FamilyScenarioSettings;
  annual_points: AnnualRunwayPoint[];
  goal_health: GoalHealth[];
  passive_income: PassiveIncomeAnalysis | null;
  ending_financial_assets_inr: number;
  ending_property_value_inr: number;
  ending_total_net_worth_inr: number;
  first_underfunded_goal_key: string | null;
};

export type FamilyPlanResponse = {
  primary_goal: PrimaryGoalResponse;
  calculated_on: string;
  snapshot_id: string | null;
  data_health: WealthDataHealth;
  assumptions: FamilyPlanAssumptions;
  goals: LinkedGoalSettings[];
  scenario_projections: FamilyScenarioProjection[];
};

export type FamilyPlanUpdate = {
  primary_goal?: GoalSettings;
  assumptions: FamilyPlanAssumptions;
  scenarios: FamilyScenarioSettings[];
  goals: LinkedGoalSettings[];
};
