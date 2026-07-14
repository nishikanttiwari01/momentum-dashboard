import axios from 'axios';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { commitWorkbook, fetchPrimaryGoal, previewWorkbook, updatePrimaryGoal } from './wealthApi';
import type { GoalConfigurationUpdate, PrimaryGoalResponse } from './wealthTypes';

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
});
