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
