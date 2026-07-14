import type { ProblemLocationPart } from './wealthTypes';

const indianNumber = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 });

export type GoalFormFieldKey =
  | 'target'
  | 'deadline'
  | `scenarios.${number}.annual_return_pct`
  | `scenarios.${number}.monthly_contribution`;

export function progressFill(progress: number): number {
  return Math.min(100, Math.max(0, progress));
}

export function formatIndianCurrency(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return '—';
  const sign = value < 0 ? '-' : '';
  return `${sign}₹${indianNumber.format(Math.abs(value))}`;
}

export function formatCompactCrore(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return '—';
  const sign = value < 0 ? '-' : '';
  return `${sign}₹${indianNumber.format(Math.abs(value) / 10_000_000)} Cr`;
}

export function goalErrorFieldKey(loc: ProblemLocationPart[]): GoalFormFieldKey | null {
  const path = loc[0] === 'body' ? loc.slice(1) : loc;
  if (path[0] === 'goal' && path[1] === 'target_amount_inr') return 'target';
  if (path[0] === 'goal' && path[1] === 'deadline') return 'deadline';

  const [section, index, field] = path;
  if (section !== 'scenarios' || typeof index !== 'number') return null;
  if (field === 'annual_return_pct') return `scenarios.${index}.annual_return_pct`;
  if (field === 'monthly_contribution_inr') return `scenarios.${index}.monthly_contribution`;
  return null;
}
