/**
 * Generated manually to sync with BuyEvaluation schema.
 */
import type { BuyCheck } from './buyCheck';

export interface BuyEvaluation {
  flag: boolean;
  profile?: string;
  mode?: 'EOD' | 'INTRADAY';
  pass_count: number;
  total_count: number;
  checks: BuyCheck[];
  failed_codes: string[];
  enforced_checks?: string[] | null;
  reasons_inline?: string | null;
  eval_ts?: string | null;
}
