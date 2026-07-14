import { describe, expect, it } from 'vitest';
import {
  formatCompactCrore,
  formatIndianCurrency,
  goalErrorFieldKey,
  progressFill,
} from './wealthGoalMath';

describe('wealth goal display helpers', () => {
  it.each([
    [125, 100],
    [-10, 0],
    [42.5, 42.5],
  ])('clamps progress fill %s to %s', (progress, expected) => {
    expect(progressFill(progress)).toBe(expected);
  });

  it('formats crore values compactly, including negative shortfalls', () => {
    expect(formatCompactCrore(150_000_000)).toBe('₹15 Cr');
    expect(formatCompactCrore(-20_000_000)).toBe('-₹2 Cr');
  });

  it('formats Indian currency and uses an em dash for missing values', () => {
    expect(formatIndianCurrency(1_50_000)).toBe('₹1,50,000');
    expect(formatIndianCurrency(-1_50_000)).toBe('-₹1,50,000');
    expect(formatIndianCurrency(null)).toBe('—');
    expect(formatCompactCrore(null)).toBe('—');
  });

  it('maps backend deadline errors to the stable deadline field key', () => {
    expect(goalErrorFieldKey(['body', 'goal', 'deadline'])).toBe('deadline');
  });

  it('maps indexed scenario errors to stable form field keys', () => {
    expect(goalErrorFieldKey(['body', 'scenarios', 1, 'annual_return_pct'])).toBe(
      'scenarios.1.annual_return_pct',
    );
    expect(goalErrorFieldKey(['body', 'scenarios', 2, 'monthly_contribution_inr'])).toBe(
      'scenarios.2.monthly_contribution',
    );
  });

  it('maps target errors and ignores unrecognized locations', () => {
    expect(goalErrorFieldKey(['body', 'goal', 'target_amount_inr'])).toBe('target');
    expect(goalErrorFieldKey(['body', 'unknown'])).toBeNull();
  });
});
