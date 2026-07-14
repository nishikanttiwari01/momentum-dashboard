import { describe, expect, it } from 'vitest';
import type { PrimaryGoalResponse } from './wealthTypes';
import { GOAL_LINE_COLORS, mergeGoalTrajectories, prefersReducedMotion } from './WealthGoalChart';

describe('WealthGoalChart', () => {
  it('uses exactly four line colors without area or gradient configuration', () => {
    expect(GOAL_LINE_COLORS).toEqual({ required: '#64748B', conservative: '#F59E0B', expected: '#2563EB', optimistic: '#059669' });
    expect(Object.keys(GOAL_LINE_COLORS)).toHaveLength(4);
    expect(JSON.stringify(GOAL_LINE_COLORS)).not.toMatch(/area|gradient/i);
  });
  it('merges and sorts required and scenario trajectories by date', () => {
    const data = {
      required_trajectory: [{ on: '2029-12-31', balance_inr: 150 }, { on: '2026-07-14', balance_inr: 100 }],
      scenario_projections: [{ settings: { scenario_key: 'expected' }, trajectory: [{ on: '2026-07-14', balance_inr: 101 }, { on: '2029-12-31', balance_inr: 180 }] }],
    } as PrimaryGoalResponse;
    expect(mergeGoalTrajectories(data)).toEqual([
      { on: '2026-07-14', required: 100, expected: 101 },
      { on: '2029-12-31', required: 150, expected: 180 },
    ]);
  });
  it('reads reduced-motion preference safely with and without a browser source', () => {
    expect(prefersReducedMotion(undefined)).toBe(false);
    expect(prefersReducedMotion({ matchMedia: () => ({ matches: true }) })).toBe(true);
    expect(prefersReducedMotion({ matchMedia: () => ({ matches: false }) })).toBe(false);
  });
});
