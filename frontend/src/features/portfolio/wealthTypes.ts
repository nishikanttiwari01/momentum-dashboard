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
