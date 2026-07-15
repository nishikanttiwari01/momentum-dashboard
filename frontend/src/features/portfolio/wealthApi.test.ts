import axios from 'axios';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  commitWorkbook,
  fetchFamilyPlan,
  fetchPrimaryGoal,
  previewWorkbook,
  restoreFamilyPlanDefaults,
  updateFamilyPlan,
  updatePrimaryGoal,
} from './wealthApi';
import type {
  FamilyPlanResponse,
  FamilyPlanUpdate,
  GoalConfigurationUpdate,
  PrimaryGoalResponse,
} from './wealthTypes';

vi.mock('axios');
const mockedAxios = vi.mocked(axios, true);

describe('wealthApi', () => {
  beforeEach(() => vi.clearAllMocks());

  it('uploads the workbook using multipart FormData', async () => {
    mockedAxios.post.mockResolvedValueOnce({ data: { preview_token: 'p1' } });
    const file = new File(['xlsx'], 'investment.xlsx');
    await previewWorkbook(file);
    const [url, body] = mockedAxios.post.mock.calls[0];
    expect(url).toBe('/api/v1/wealth-portfolio/imports/preview');
    expect(body).toBeInstanceOf(FormData);
    expect((body as FormData).get('workbook')).toBe(file);
  });

  it('commits the selected preview token', async () => {
    mockedAxios.post.mockResolvedValueOnce({ data: { snapshot_id: 's1', created: true } });
    await commitWorkbook('p1');
    expect(mockedAxios.post).toHaveBeenCalledWith('/api/v1/wealth-portfolio/imports/p1/commit');
  });

  it('fetches the primary wealth goal and returns the response data', async () => {
    const goal = {
      goal: { name: '₹15 Cr by 2029', target_amount_inr: 150_000_000, deadline: '2029-12-31' },
      scenario_projections: [],
      calculated_on: '2026-07-14',
      snapshot_id: null,
      current_value_inr: null,
      achieved_pct: null,
      remaining_inr: null,
      required_monthly_contribution_inr: null,
      required_trajectory: [],
      data_health: 'empty',
    } satisfies PrimaryGoalResponse;
    mockedAxios.get.mockResolvedValueOnce({ data: goal });

    const result = await fetchPrimaryGoal();

    expect(mockedAxios.get).toHaveBeenCalledWith('/api/v1/wealth-portfolio/goals/primary');
    expect(result).toBe(goal);
  });

  it('puts the complete primary goal configuration and returns the response data', async () => {
    const payload = {
      goal: { name: 'Financial freedom', target_amount_inr: 200_000_000, deadline: '2035-12-31' },
      scenarios: [
        { scenario_key: 'conservative', annual_return_pct: 8, monthly_contribution_inr: 100_000 },
        { scenario_key: 'expected', annual_return_pct: 11, monthly_contribution_inr: 150_000 },
        { scenario_key: 'optimistic', annual_return_pct: 14, monthly_contribution_inr: 200_000 },
      ],
    } satisfies GoalConfigurationUpdate;
    const response = { goal: payload.goal } as PrimaryGoalResponse;
    mockedAxios.put.mockResolvedValueOnce({ data: response });

    const result = await updatePrimaryGoal(payload);

    expect(mockedAxios.put).toHaveBeenCalledWith(
      '/api/v1/wealth-portfolio/goals/primary',
      payload,
    );
    expect(result).toBe(response);
  });

  const familyPlan = {
    primary_goal: {
      goal: { name: 'Freedom', target_amount_inr: 150_000_000, deadline: '2045-12-31' },
      scenario_projections: [], calculated_on: '2026-07-15', snapshot_id: 'snapshot-1',
      current_value_inr: 50_000_000, achieved_pct: 33.33, remaining_inr: 100_000_000,
      required_monthly_contribution_inr: 200_000, required_trajectory: [], data_health: 'fresh',
    },
    calculated_on: '2026-07-15', snapshot_id: 'snapshot-1', data_health: 'fresh',
    assumptions: {
      monthly_contribution_inr: 200_000, contribution_step_up_enabled: true,
      contribution_step_up_pct: 8, monthly_rent_inr: 50_000, rent_growth_pct: 5,
      reinvest_rent_until: '2035-12-31', property_growth_pct: 6,
      withdrawal_rate_pct: 4, amber_margin_pct: 10,
    },
    goals: [{
      goal_key: 'education', name: 'Education', goal_type: 'education',
      current_value_amount_inr: 5_000_000, target_date: '2032-06-30', inflation_pct: 8,
      funding_treatment: 'expense', priority: 1, enabled: true, display_order: 0,
    }],
    scenario_projections: [{
      settings: { scenario_key: 'expected', annual_return_pct: 11 },
      annual_points: [{
        on: '2027-12-31', financial_assets_inr: 55_000_000, property_value_inr: 20_000_000,
        total_net_worth_inr: 75_000_000, annual_contributions_inr: 2_400_000,
        annual_rent_inr: 600_000, financial_growth_inr: 5_000_000, property_growth_inr: 1_000_000,
        goal_outflows_inr: 0, events: [],
      }],
      goal_health: [{
        goal: {
          goal_key: 'education', name: 'Education', goal_type: 'education',
          current_value_amount_inr: 5_000_000, target_date: '2032-06-30', inflation_pct: 8,
          funding_treatment: 'expense', priority: 1, enabled: true, display_order: 0,
        },
        inflated_cost_inr: 8_000_000, available_before_inr: 9_000_000,
        funded_amount_inr: 8_000_000, shortfall_inr: 0, funded_pct: 100,
        status: 'green', reason: 'Fully funded',
      }],
      passive_income: {
        target_date: '2040-12-31', target_monthly_income_inr: 200_000,
        projected_monthly_rent_inr: 75_000, portfolio_monthly_gap_inr: 125_000,
        required_corpus_inr: 37_500_000, supported_portfolio_monthly_income_inr: 150_000,
        total_monthly_income_inr: 225_000, surplus_or_shortfall_inr: 25_000,
        on_track: true, later_goals_protected: true, earliest_sustainable_date: null,
      },
      ending_financial_assets_inr: 80_000_000, ending_property_value_inr: 30_000_000,
      ending_total_net_worth_inr: 110_000_000, first_underfunded_goal_key: null,
    }],
  } satisfies FamilyPlanResponse;

  it('gets the family plan and returns response data', async () => {
    mockedAxios.get.mockResolvedValueOnce({ data: familyPlan });
    await expect(fetchFamilyPlan()).resolves.toBe(familyPlan);
    expect(mockedAxios.get).toHaveBeenCalledWith('/api/v1/wealth-portfolio/goals/family-plan');
  });

  it('puts the complete family plan update and returns response data', async () => {
    const payload = {
      assumptions: familyPlan.assumptions,
      goals: familyPlan.goals,
      scenarios: [{ scenario_key: 'expected', annual_return_pct: 11 }],
    } satisfies FamilyPlanUpdate;
    mockedAxios.put.mockResolvedValueOnce({ data: familyPlan });
    await expect(updateFamilyPlan(payload)).resolves.toBe(familyPlan);
    expect(mockedAxios.put).toHaveBeenCalledWith('/api/v1/wealth-portfolio/goals/family-plan', payload);
  });

  it('posts to restore family plan defaults and returns response data', async () => {
    mockedAxios.post.mockResolvedValueOnce({ data: familyPlan });
    await expect(restoreFamilyPlanDefaults()).resolves.toBe(familyPlan);
    expect(mockedAxios.post).toHaveBeenCalledWith('/api/v1/wealth-portfolio/goals/family-plan/restore-defaults');
  });
});
