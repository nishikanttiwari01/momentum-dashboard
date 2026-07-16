import { describe, expect, it } from 'vitest';
import {
  familyPlanProblemField,
  familyRunwayRows,
  formatCrore,
  formatMonthlyIncome,
  goalStatusColor,
} from './familyWealthMath';
import type { FamilyScenarioProjection } from './wealthTypes';

const projection = (
  scenario_key: 'conservative' | 'expected' | 'optimistic',
  points: FamilyScenarioProjection['annual_points'],
): FamilyScenarioProjection => ({
  settings: { scenario_key, annual_return_pct: 10 }, annual_points: points,
  goal_health: [], passive_income: null, ending_financial_assets_inr: 0,
  ending_property_value_inr: 0, ending_total_net_worth_inr: 0,
  first_underfunded_goal_key: null,
});

const point = (on: string, total: number, events: FamilyScenarioProjection['annual_points'][number]['events'] = []) => ({
  on, financial_assets_inr: total * 0.8, property_value_inr: total * 0.2,
  total_net_worth_inr: total, annual_contributions_inr: 0, annual_rent_inr: 0,
  financial_growth_inr: 0, property_growth_inr: 0, goal_outflows_inr: 0, events,
});

describe('familyRunwayRows', () => {
  it('merges scenario points by date in chronological order without index alignment', () => {
    const projections = [
      projection('optimistic', [point('2028-12-31', 300), point('2026-12-31', 100)]),
      projection('expected', [point('2027-12-31', 180)]),
      projection('conservative', [point('2026-12-31', 80), point('2028-12-31', 200)]),
    ];
    const before = structuredClone(projections);
    expect(familyRunwayRows(projections)).toEqual([
      { on: '2026-12-31', year: 2026, conservative_total_inr: 80, conservative_financial_assets_inr: 64, conservative_property_value_inr: 16, optimistic_total_inr: 100, optimistic_financial_assets_inr: 80, optimistic_property_value_inr: 20, events: [] },
      { on: '2027-12-31', year: 2027, expected_total_inr: 180, expected_financial_assets_inr: 144, expected_property_value_inr: 36, events: [] },
      { on: '2028-12-31', year: 2028, conservative_total_inr: 200, conservative_financial_assets_inr: 160, conservative_property_value_inr: 40, optimistic_total_inr: 300, optimistic_financial_assets_inr: 240, optimistic_property_value_inr: 60, events: [] },
    ]);
    expect(projections).toEqual(before);
  });

  it('keeps numeric zero and normalized expected events', () => {
    const events = [{ goal_key: 'home', goal_name: 'Home', goal_type: 'house' as const,
      funding_treatment: 'asset_conversion' as const, amount_inr: 10, funded_amount_inr: 10, shortfall_inr: 0 }];
    const rows = familyRunwayRows([projection('expected', [point('2026-12-31', 0, events)])]);
    expect(rows[0]).toMatchObject({
      expected_total_inr: 0, expected_financial_assets_inr: 0, expected_property_value_inr: 0,
      events: [{ goal_key: 'home', label: 'Home', amount_inr: 10, funded_amount_inr: 10, shortfall_inr: 0 }],
    });
    expect(rows[0].events).not.toBe(events);
    expect(rows[0].events[0]).not.toBe(events[0]);
  });
});

describe('family wealth formatting', () => {
  it.each([[null, '—'], [0, '₹0'], [10_000_000, '₹1 Cr'], [15_500_000, '₹1.55 Cr'], [-20_000_000, '-₹2 Cr']])(
    'formats %s as crore label %s', (value, expected) => expect(formatCrore(value)).toBe(expected),
  );
  it.each([[null, '—'], [0, '₹0/month'], [150_000, '₹1,50,000/month'], [-25_000, '-₹25,000/month']])(
    'formats %s as monthly income %s', (value, expected) => expect(formatMonthlyIncome(value)).toBe(expected),
  );
});

it('maps goal statuses to an accessible semantic palette', () => {
  expect(goalStatusColor('green')).toBe('#137333');
  expect(goalStatusColor('amber')).toBe('#9A6700');
  expect(goalStatusColor('red')).toBe('#B3261E');
});

it('maps problem locations to stable field keys', () => {
  expect(familyPlanProblemField(['body', 'assumptions', 'monthly_contribution_inr'])).toBe('assumptions.monthly_contribution_inr');
  expect(familyPlanProblemField(['body', 'goals', 2, 'target_date'])).toBe('goals.2.target_date');
  expect(familyPlanProblemField(['scenarios', 1, 'annual_return_pct'])).toBe('scenarios.1.annual_return_pct');
  expect(familyPlanProblemField(['body', 'unrelated'])).toBeNull();
  expect(familyPlanProblemField([])).toBeNull();
});
