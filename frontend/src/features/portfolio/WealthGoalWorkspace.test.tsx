import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import type { PrimaryGoalResponse } from './wealthTypes';
import {
  DEFAULT_GOAL_FORM,
  EmptyWealthGoalAlert,
  WealthGoalError,
  WealthGoalLoading,
  WealthGoalWorkspaceView,
  applyGoalFormChange,
  applyGoalMutationSuccess,
  goalFormFromResponse,
  goalUpdateFromForm,
  wealthGoalQueryOptions,
} from './WealthGoalWorkspace';

const response: PrimaryGoalResponse = {
  goal: { name: 'Financial freedom', target_amount_inr: 150_000_000, deadline: '2029-12-31' },
  calculated_on: '2026-07-14', snapshot_id: 'snapshot-1', current_value_inr: 184_500_000,
  achieved_pct: 123, remaining_inr: 0, required_monthly_contribution_inr: 250_000,
  data_health: 'warning', required_trajectory: [{ on: '2026-07-14', balance_inr: 184_500_000 }, { on: '2029-12-31', balance_inr: 150_000_000 }],
  scenario_projections: [
    ['conservative', 7, 0, 210_000_000, 60_000_000, true, '2028-12-01'],
    ['expected', 10, 25_000, 240_000_000, 90_000_000, true, '2028-04-01'],
    ['optimistic', 13, 50_000, 280_000_000, 130_000_000, true, null],
  ].map(([scenario_key, annual_return_pct, monthly_contribution_inr, projected_deadline_value_inr, surplus_or_shortfall_inr, on_track, projected_completion_date]) => ({
    settings: { scenario_key, annual_return_pct, monthly_contribution_inr }, projected_deadline_value_inr,
    surplus_or_shortfall_inr, on_track, projected_completion_date,
    trajectory: [{ on: '2026-07-14', balance_inr: 184_500_000 }, { on: '2029-12-31', balance_inr: projected_deadline_value_inr }],
  })) as PrimaryGoalResponse['scenario_projections'],
};

const renderView = (data: PrimaryGoalResponse = response) => renderToStaticMarkup(
  <WealthGoalWorkspaceView data={data} onSave={vi.fn()} isSaving={false} />,
);

describe('WealthGoalWorkspace', () => {
  it('renders the finish line, unclamped number, warning health and all scenarios', () => {
    const html = renderView();
    expect(html).toContain('Financial freedom');
    expect(html).toContain('123% achieved');
    expect(html).toContain('data-progress-fill="100"');
    expect(html).toContain('Attention needed');
    for (const label of ['Conservative', 'Expected', 'Optimistic']) expect(html).toContain(label);
  });

  it('keeps an empty snapshot editable and opens workbook import from its CTA', () => {
    const onOpenDataImport = vi.fn();
    const alert = EmptyWealthGoalAlert({ onOpenDataImport });
    alert.props.action.props.onClick();
    expect(onOpenDataImport).toHaveBeenCalledOnce();
    expect(alert.props.action.props.children).toBe('Import workbook');
    const html = renderToStaticMarkup(<WealthGoalWorkspaceView data={{ ...response, snapshot_id: null, current_value_inr: null, achieved_pct: null, data_health: 'empty' }} onSave={vi.fn()} isSaving={false} onOpenDataImport={onOpenDataImport} />);
    expect(html).toContain('Import investment.xlsx');
    expect(html).toContain('Import workbook');
    expect(html).toContain('Target amount');
  });

  it('renders stable loading and wires error retry to refetch', () => {
    expect(renderToStaticMarkup(<WealthGoalLoading />)).toContain('min-height:640px');
    const retry = vi.fn();
    const element = WealthGoalError({ retry });
    element.props.action.props.onClick();
    expect(retry).toHaveBeenCalledOnce();
    const error = renderToStaticMarkup(element);
    expect(error).toContain('No estimates are shown');
    expect(error).not.toContain('₹');
    expect(wealthGoalQueryOptions.queryKey).toEqual(['wealth-primary-goal']);
    expect(wealthGoalQueryOptions.retry).toBe(1);
  });

  it('edits expected return and submits the complete payload', () => {
    const original = goalFormFromResponse(response);
    const form = applyGoalFormChange(original, { type: 'scenario', index: 1, field: 'annual_return_pct', value: '11.5' });
    expect(form).not.toEqual(original);
    expect(renderToStaticMarkup(<WealthGoalWorkspaceView data={response} initialForm={form} onSave={vi.fn()} isSaving={false} />)).toContain('Unsaved changes');
    expect(goalUpdateFromForm(form)).toEqual({
      goal: { name: 'Financial freedom', target_amount_inr: 150_000_000, deadline: '2029-12-31' },
      scenarios: [
        { scenario_key: 'conservative', annual_return_pct: 7, monthly_contribution_inr: 0 },
        { scenario_key: 'expected', annual_return_pct: 11.5, monthly_contribution_inr: 25_000 },
        { scenario_key: 'optimistic', annual_return_pct: 13, monthly_contribution_inr: 50_000 },
      ],
    });
  });

  it('restores visible default inputs without saving until submit', () => {
    const onSave = vi.fn();
    const restored = applyGoalFormChange(goalFormFromResponse(response), { type: 'restore' });
    expect(restored).toEqual(DEFAULT_GOAL_FORM);
    expect(onSave).not.toHaveBeenCalled();
    onSave(goalUpdateFromForm(restored));
    expect(onSave).toHaveBeenCalledOnce();
  });

  it('renders inline indexed errors without replacing entered values', () => {
    const html = renderToStaticMarkup(<WealthGoalWorkspaceView data={response} onSave={vi.fn()} isSaving={false}
      initialForm={{ ...goalFormFromResponse(response), deadline: '2020-01-01' }}
      fieldErrors={{ deadline: 'Deadline must be in the future', 'scenarios.1.annual_return_pct': 'Return is too high' }} />);
    expect(html).toContain('2020-01-01');
    expect(html).toContain('Deadline must be in the future');
    expect(html).toContain('Return is too high');
  });

  it('shows a concise saved confirmation', () => expect(renderToStaticMarkup(
    <WealthGoalWorkspaceView data={response} onSave={vi.fn()} isSaving={false} saved />,
  )).toContain('Goal settings saved'));

  it('updates and invalidates the primary-goal cache after mutation success', () => {
    const client = { setQueryData: vi.fn(), invalidateQueries: vi.fn().mockResolvedValue(undefined) };
    applyGoalMutationSuccess(client, response);
    expect(client.setQueryData).toHaveBeenCalledWith(['wealth-primary-goal'], response);
    expect(client.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['wealth-primary-goal'] });
  });
});
