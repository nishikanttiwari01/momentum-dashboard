import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import type { PrimaryGoalResponse } from './wealthTypes';
import type { FamilyPlanResponse, FamilyScenarioProjection, GoalHealth, PassiveIncomeAnalysis } from './wealthTypes';
import { FamilyPlanAssumptions, familyPlanDraftFromResponse, familyPlanUpdateFromDraft } from './FamilyPlanAssumptions';
import { FamilyWealthRunwayChart, RUNWAY_LINE_ANIMATION_ACTIVE, RunwayTooltipContent, aggregateRunwayEvents, runwayTooltipLines } from './FamilyWealthRunwayChart';
import { FamilyGoalCards } from './FamilyGoalCards';
import { PassiveIncomePanel, type PassiveIncomePanelData } from './PassiveIncomePanel';
import {
  DEFAULT_GOAL_FORM,
  EmptyWealthGoalAlert,
  WealthGoalError,
  WealthGoalLoading,
  WealthGoalWorkspaceView,
  FamilyPlanWorkspaceView,
  applyGoalFormChange,
  applyGoalMutationSuccess,
  applyUserGoalFormChange,
  classifyGoalSaveError,
  clearGoalSaveFeedback,
  createGoalFormState,
  goalFormReducer,
  goalSubmissionFromState,
  isGoalSaveDisabled,
  retryGoalSave,
  goalFormFromResponse,
  goalUpdateFromForm,
  wealthGoalQueryOptions,
  familyPlanQueryOptions,
  classifyFamilyPlanSaveError,
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
    expect(html).toContain('role="img"');
    expect(html).toContain('Required path compared with conservative');
    for (const label of ['Conservative', 'Expected', 'Optimistic']) expect(html).toContain(label);
  });

  it('formats achieved progress to at most two decimals without changing the raw progress fill', () => {
    const html = renderView({ ...response, achieved_pct: 0.32866666666666666 });
    expect(html).toContain('0.33% achieved');
    expect(html).toContain('aria-label="Goal progress 0.33%"');
    expect(html).toContain('data-progress-fill="0.32866666666666666"');
    expect(html).not.toContain('0.32866666666666666%');
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

  it('preserves a dirty expected return when refreshed server data changes', () => {
    const initial = createGoalFormState(goalFormFromResponse(response));
    const dirty = goalFormReducer(initial, { type: 'change', change: { type: 'scenario', index: 1, field: 'annual_return_pct', value: '11.5' } });
    const refreshed = goalFormFromResponse({ ...response, goal: { ...response.goal, target_amount_inr: 160_000_000 } });
    const synced = goalFormReducer(dirty, { type: 'serverSync', form: refreshed });
    expect(synced.draft.scenarios[1].annual_return_pct).toBe('11.5');
    expect(synced.accepted.target).toBe('160000000');
    expect(synced.dirty).toBe(true);
  });

  it('syncs refreshed server data while pristine', () => {
    const initial = createGoalFormState(goalFormFromResponse(response));
    const refreshed = goalFormFromResponse({ ...response, goal: { ...response.goal, target_amount_inr: 160_000_000 } });
    const synced = goalFormReducer(initial, { type: 'serverSync', form: refreshed });
    expect(synced.draft).toEqual(refreshed);
    expect(synced.dirty).toBe(false);
  });

  it('treats a supplied initial form as a draft against the server baseline', () => {
    const accepted = goalFormFromResponse(response);
    const draft = applyGoalFormChange(accepted, { type: 'scenario', index: 1, field: 'annual_return_pct', value: '11.5' });
    expect(createGoalFormState(accepted, draft)).toMatchObject({ accepted, draft, dirty: true, saved: false });
  });

  it('restores visible default inputs without saving until submit', () => {
    const onSave = vi.fn();
    const restored = applyGoalFormChange(goalFormFromResponse(response), { type: 'restore' });
    expect(restored).toEqual(DEFAULT_GOAL_FORM);
    expect(restored.name).toBe('₹15 Cr by 2029');
    expect(onSave).not.toHaveBeenCalled();
    onSave(goalUpdateFromForm(restored));
    expect(onSave).toHaveBeenCalledOnce();
  });

  it('tracks dirty transitions and clears saved confirmation on edit or restore', () => {
    const saved = goalFormReducer(createGoalFormState(goalFormFromResponse(response)), { type: 'saveSuccess', form: goalFormFromResponse(response) });
    expect(saved.saved).toBe(true);
    const edited = goalFormReducer(saved, { type: 'change', change: { type: 'field', field: 'deadline', value: '2030-01-01' } });
    expect(edited).toMatchObject({ dirty: true, saved: false });
    const restored = goalFormReducer(saved, { type: 'change', change: { type: 'restore' } });
    expect(restored.saved).toBe(false);
    expect(restored.dirty).toBe(JSON.stringify(DEFAULT_GOAL_FORM) !== JSON.stringify(saved.accepted));
  });

  it('disables save when pristine and exposes the attempted payload for retry after a generic failure', () => {
    const initial = createGoalFormState(goalFormFromResponse(response));
    expect(initial.dirty).toBe(false);
    expect(isGoalSaveDisabled(initial, false)).toBe(true);
    const dirty = goalFormReducer(initial, { type: 'change', change: { type: 'scenario', index: 1, field: 'annual_return_pct', value: '11.5' } });
    expect(isGoalSaveDisabled(dirty, false)).toBe(false);
    expect(isGoalSaveDisabled(dirty, true)).toBe(true);
    const payload = goalSubmissionFromState(dirty);
    const retry = vi.fn();
    retryGoalSave({ payload }, retry);
    expect(retry).toHaveBeenCalledWith(payload);
  });

  it('clears production save feedback before dispatching every user draft change', () => {
    const onDraftChange = vi.fn(() => expect(clearGoalSaveFeedback()).toEqual({ saved: false, error: null }));
    const dispatch = vi.fn();
    const change = { type: 'restore' } as const;
    applyUserGoalFormChange(change, onDraftChange, dispatch);
    expect(onDraftChange).toHaveBeenCalledOnce();
    expect(dispatch).toHaveBeenCalledWith({ type: 'change', change });
    expect(onDraftChange.mock.invocationCallOrder[0]).toBeLessThan(dispatch.mock.invocationCallOrder[0]);
  });

  it('disables all editable fields, restore, and import while saving', () => {
    const html = renderToStaticMarkup(<WealthGoalWorkspaceView data={{ ...response, data_health: 'empty' }} initialForm={applyGoalFormChange(goalFormFromResponse(response), { type: 'field', field: 'deadline', value: '2030-01-01' })} onSave={vi.fn()} isSaving saveError="Save failed" onRetrySave={vi.fn()} onOpenDataImport={vi.fn()} />);
    expect(html.match(/<input[^>]*disabled=""/g)).toHaveLength(8);
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>Restore defaults<\/button>/);
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>Import workbook<\/button>/);
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>Retry<\/button>/);
  });

  it('uses backend annual-return constraints for every scenario input', () => {
    const html = renderView();
    for (const label of ['Conservative', 'Expected', 'Optimistic']) expect(html).toContain(`${label} annual return`);
    expect(html.match(/<input[^>]*min="-25"[^>]*max="50"[^>]*step="0.1"/g)).toHaveLength(3);
  });

  it('classifies 422 field problems separately from retryable form errors', () => {
    const fieldError = { isAxiosError: true, response: { status: 422, data: { errors: [{ loc: ['body', 'goal', 'deadline'], msg: 'Future date required' }] } } };
    expect(classifyGoalSaveError(fieldError)).toEqual({ kind: 'fields', errors: { deadline: 'Future date required' } });
    expect(classifyGoalSaveError({ isAxiosError: true, response: { status: 500 } })).toEqual({ kind: 'form', message: 'Could not save goal settings. Please try again.' });
    expect(classifyGoalSaveError(new Error('offline'))).toEqual({ kind: 'form', message: 'Could not save goal settings. Please try again.' });
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

const linkedGoals: GoalHealth[] = [
  ['education', 'School fees', '2028-06-01', 'green', 'Fully reserved', 100, 2_000_000, 2_200_000, 2_000_000, 0],
  ['house', 'Family home', '2029-01-01', 'amber', 'Within the planning margin', 82, 8_000_000, 7_000_000, 6_560_000, 1_440_000],
  ['marriage', 'Wedding', '2031-03-01', 'red', 'Funding gap remains', 40, 3_000_000, 1_200_000, 1_200_000, 1_800_000],
  ['passive_income', 'Income freedom', '2029-12-31', 'green', 'Income target sustained', 110, 60_000_000, 66_000_000, 60_000_000, 0],
].map(([goal_type, name, target_date, status, reason, funded_pct, inflated_cost_inr, available_before_inr, funded_amount_inr, shortfall_inr], index) => ({
  goal: { goal_key: String(goal_type), name: String(name), goal_type, current_value_amount_inr: Number(inflated_cost_inr), target_date: String(target_date), inflation_pct: 6, funding_treatment: goal_type === 'house' ? 'asset_conversion' : goal_type === 'passive_income' ? 'income_target' : 'expense', priority: index + 1, enabled: true, display_order: index + 1 },
  inflated_cost_inr: Number(inflated_cost_inr), available_before_inr: Number(available_before_inr), funded_amount_inr: Number(funded_amount_inr), shortfall_inr: Number(shortfall_inr), funded_pct: Number(funded_pct), status, reason: String(reason),
})) as GoalHealth[];

const runwayProjection: FamilyScenarioProjection = {
  settings: { scenario_key: 'expected', annual_return_pct: 10 },
  annual_points: [{ on: '2029-12-31', financial_assets_inr: 120_000_000, property_value_inr: 50_000_000, total_net_worth_inr: 170_000_000, annual_contributions_inr: 2_400_000, annual_rent_inr: 1_200_000, financial_growth_inr: 9_000_000, property_growth_inr: 3_000_000, goal_outflows_inr: 8_000_000, events: linkedGoals.slice(0, 2).map(({ goal }, index) => ({ goal_key: goal.goal_key, goal_name: goal.name, goal_type: goal.goal_type, funding_treatment: goal.funding_treatment, amount_inr: index ? 8_000_000 : 2_000_000, funded_amount_inr: index ? 6_560_000 : 2_000_000, shortfall_inr: index ? 1_440_000 : 0 })) }],
  goal_health: linkedGoals, passive_income: null, ending_financial_assets_inr: 120_000_000, ending_property_value_inr: 50_000_000, ending_total_net_worth_inr: 170_000_000, first_underfunded_goal_key: 'house',
};

describe('family runway visual components', () => {
  it('provides every misaligned scenario row in a semantic annual data fallback', () => {
    const scenario = (scenario_key: FamilyScenarioProjection['settings']['scenario_key'], annual_points: FamilyScenarioProjection['annual_points']): FamilyScenarioProjection => ({ ...runwayProjection, settings: { scenario_key, annual_return_pct: 8 }, annual_points });
    const point = (on: string, total_net_worth_inr: number, financial_assets_inr = 0, property_value_inr = 0): FamilyScenarioProjection['annual_points'][number] => ({ on, total_net_worth_inr, financial_assets_inr, property_value_inr, annual_contributions_inr: 0, annual_rent_inr: 0, financial_growth_inr: 0, property_growth_inr: 0, goal_outflows_inr: 0, events: [] });
    const projections = [
      scenario('conservative', [point('2028-12-31', 80_000_000), point('2030-12-31', 100_000_000)]),
      scenario('expected', [point('2028-12-31', 100_000_000, 70_000_000, 30_000_000), runwayProjection.annual_points[0], point('2030-12-31', 200_000_000, 140_000_000, 60_000_000)]),
      scenario('optimistic', [point('2029-12-31', 190_000_000), point('2030-12-31', 230_000_000)]),
    ];
    const html = renderToStaticMarkup(<FamilyWealthRunwayChart projections={projections} />);
    for (const text of ['Annual family wealth data', '2028-12-31', '2029-12-31', '2030-12-31', '₹10 Cr', '₹12 Cr', '₹5 Cr', '₹19 Cr', '₹23 Cr', 'School fees ₹0.2 Cr']) expect(html).toContain(text);
  });

  it('exports complete tooltip facts and disables animation on line-only charts', () => {
    expect(runwayTooltipLines(runwayProjection.annual_points[0])).toEqual(expect.arrayContaining(['Annual contributions ₹0.24 Cr', 'Rent ₹0.12 Cr', 'Financial growth ₹0.9 Cr', 'Property growth ₹0.3 Cr', 'Goal outflows ₹0.8 Cr', 'School fees: funded ₹0.2 Cr', 'Family home: funded ₹0.66 Cr; shortfall ₹0.14 Cr']));
    expect(RUNWAY_LINE_ANIMATION_ACTIVE).toBe(false);
    expect(FamilyWealthRunwayChart.toString()).not.toMatch(/\bArea\b|linearGradient/);
  });

  it('renders each tooltip event funding fact exactly once', () => {
    const point = runwayProjection.annual_points[0];
    const html = renderToStaticMarkup(<RunwayTooltipContent active label={point.on} payload={[{}]} pointByDate={new Map([[point.on, point]])} />);
    expect(html.match(/School fees: funded/g)).toHaveLength(1);
    expect(html.match(/Family home: funded/g)).toHaveLength(1);
    expect(html).toContain('shortfall ₹0.14 Cr');
  });

  it('renders an accessible unfilled runway with aggregated event fallback and tooltip facts', () => {
    expect(aggregateRunwayEvents(runwayProjection.annual_points[0].events)[0].label).toContain('2 milestones');
    const html = renderToStaticMarkup(<FamilyWealthRunwayChart projections={[runwayProjection]} />);
    expect(html).toContain('Family wealth runway');
    expect(html).toContain('2029 milestones');
    expect(html).toContain('School fees');
    expect(html).toContain('Family home');
    expect(html).toContain('Transfer to property');
    expect(html).not.toContain('<linearGradient');
    expect(html).not.toContain('<path class="recharts-area');
  });

  it('renders every goal status, reason, accessible type icon and funded value', () => {
    const html = renderToStaticMarkup(<FamilyGoalCards goals={linkedGoals} />);
    for (const text of ['Green', 'Amber', 'Red', 'Fully reserved', 'Within the planning margin', 'Funding gap remains', '100% funded', '82% funded', '40% funded']) expect(html).toContain(text);
    for (const type of ['Education goal', 'House goal', 'Marriage goal', 'Passive income goal']) expect(html).toContain(`aria-label="${type}"`);
    for (const text of ['Due Jun 2028', 'Inflated target ₹0.2 Cr', 'Available before ₹0.22 Cr', 'Funded amount ₹0.2 Cr', 'Gap ₹0', 'Gap ₹0.14 Cr', 'Gap ₹0.18 Cr']) expect(html).toContain(text);
  });

  it('explains rent offset, corpus, signed outcome, protection and sustainable date', () => {
    const analysis: PassiveIncomeAnalysis = { target_date: '2032-12-31', target_monthly_income_inr: 275_000, projected_monthly_rent_inr: 70_000, portfolio_monthly_gap_inr: 205_000, required_corpus_inr: 39_000_000, supported_portfolio_monthly_income_inr: 215_000, total_monthly_income_inr: 285_000, surplus_or_shortfall_inr: 10_000, on_track: true, later_goals_protected: true, earliest_sustainable_date: '2029-06-30' };
    const html = renderToStaticMarkup(<PassiveIncomePanel analysis={analysis} />);
    for (const text of ['2032 income runway', 'Rent counts toward the ₹2,75,000/month target', '₹3.9 Cr', '+₹10,000/month', 'Later goals remain protected', '30 Jun 2029', 'On track']) expect(html).toContain(text);
  });

  it('shows specific warnings, dashes for null dates, and never leaks invalid values', () => {
    const analysis: PassiveIncomeAnalysis = { target_date: '2029-12-31', target_monthly_income_inr: 200_000, projected_monthly_rent_inr: 40_000, portfolio_monthly_gap_inr: 160_000, required_corpus_inr: 48_000_000, supported_portfolio_monthly_income_inr: 100_000, total_monthly_income_inr: 140_000, surplus_or_shortfall_inr: -60_000, on_track: false, later_goals_protected: false, earliest_sustainable_date: null };
    const html = renderToStaticMarkup(<PassiveIncomePanel analysis={analysis} />);
    expect(html).toContain('-₹60,000/month');
    expect(html).toContain('Later goals would be exposed');
    expect(html).toMatch(/Earliest sustainable date<\/span><strong[^>]*>—/);
    expect(html).not.toMatch(/NaN|undefined/);
  });

  it('keeps track and protection independent and renders nullable facts as dashes', () => {
    const analysis: PassiveIncomePanelData = { target_date: '2035-12-31', target_monthly_income_inr: 300_000, projected_monthly_rent_inr: null, portfolio_monthly_gap_inr: null, required_corpus_inr: null, supported_portfolio_monthly_income_inr: null, total_monthly_income_inr: null, surplus_or_shortfall_inr: null, on_track: true, later_goals_protected: false, earliest_sustainable_date: null };
    const html = renderToStaticMarkup(<PassiveIncomePanel analysis={analysis} />);
    expect(html).toContain('On track');
    expect(html).toContain('Later goals would be exposed');
    expect(html.match(/—/g)?.length).toBeGreaterThanOrEqual(6);
    expect(html).not.toMatch(/NaN|undefined/);
    const protectedButShort = renderToStaticMarkup(<PassiveIncomePanel analysis={{ ...analysis, on_track: false, later_goals_protected: true }} />);
    expect(protectedButShort).toContain('Shortfall');
    expect(protectedButShort).toContain('Later goals remain protected');
  });
});

const familyPlan: FamilyPlanResponse = {
  primary_goal: response,
  calculated_on: '2026-07-15', snapshot_id: 'snapshot-1', data_health: 'fresh',
  assumptions: { monthly_contribution_inr: 600000, contribution_step_up_enabled: false, contribution_step_up_pct: 6, monthly_rent_inr: 45000, rent_growth_pct: 6, reinvest_rent_until: '2029-12-31', property_growth_pct: 6, withdrawal_rate_pct: 4, amber_margin_pct: 10 },
  goals: linkedGoals.map(({ goal }) => goal),
  scenario_projections: [
    { ...runwayProjection, settings: { scenario_key: 'conservative', annual_return_pct: 7 } },
    runwayProjection,
    { ...runwayProjection, settings: { scenario_key: 'optimistic', annual_return_pct: 13 } },
  ],
};

describe('family plan assumptions', () => {
  it('shows the six lakh default and disables the six percent step-up until selected', () => {
    const draft = familyPlanDraftFromResponse(familyPlan);
    const html = renderToStaticMarkup(<FamilyPlanAssumptions value={draft} onChange={vi.fn()} fieldErrors={{}} disabled={false} />);
    expect(html).toContain('Monthly investment');
    expect(html).toContain('value="600000"');
    expect(html).toContain('Annual contribution step-up');
    expect(html).toMatch(/<input[^>]*disabled=""[^>]*value="6"/);
  });

  it('builds one atomic payload containing assumptions, three scenarios and all linked goals', () => {
    const draft = familyPlanDraftFromResponse(familyPlan);
    draft.assumptions.monthly_contribution_inr = '650000';
    draft.assumptions.contribution_step_up_enabled = true;
    const payload = familyPlanUpdateFromDraft(draft);
    expect(payload.assumptions.monthly_contribution_inr).toBe(650000);
    expect(payload.assumptions.contribution_step_up_pct).toBe(6);
    expect(payload.scenarios.map(({ scenario_key }) => scenario_key)).toEqual(['conservative', 'expected', 'optimistic']);
    expect(payload.goals).toHaveLength(linkedGoals.length);
  });

  it('labels draft assumptions honestly before a server calculation is saved', () => {
    const draft = familyPlanDraftFromResponse(familyPlan);
    draft.assumptions.monthly_contribution_inr = '650000';
    const html = renderToStaticMarkup(<FamilyPlanAssumptions value={draft} onChange={vi.fn()} fieldErrors={{}} disabled={false} dirty />);
    expect(html).toContain('Draft assumptions');
    expect(html).toContain('Charts still show the last saved calculation');
  });

  it('keeps the pinned goal before the runway and exposes saved scenario analysis', () => {
    const draft = familyPlanDraftFromResponse(familyPlan);
    const html = renderToStaticMarkup(<FamilyPlanWorkspaceView data={familyPlan} draft={draft} onDraftChange={vi.fn()} onSave={vi.fn()} onRestore={vi.fn()} isSaving={false} />);
    expect(html.indexOf('Primary family finish line')).toBeLessThan(html.indexOf('Family wealth runway'));
    expect(html.indexOf('Family wealth runway')).toBeLessThan(html.indexOf('Linked goals'));
    expect(html.indexOf('Linked goals')).toBeLessThan(html.indexOf('Scenario comparison'));
    expect(html).toContain('Edit assumptions');
    expect(familyPlanQueryOptions.queryKey).toEqual(['wealth-family-plan']);
  });

  it('maps server validation fields and keeps generic failures retryable', () => {
    const problem = { isAxiosError: true, response: { status: 422, data: { errors: [{ loc: ['body', 'goals', 1, 'target_date'], msg: 'Choose a later date' }] } } };
    expect(classifyFamilyPlanSaveError(problem)).toEqual({ kind: 'fields', errors: { 'goals.1.target_date': 'Choose a later date' } });
    expect(classifyFamilyPlanSaveError(new Error('offline'))).toEqual({ kind: 'form', message: 'Could not calculate the updated family plan. Your last saved plan is unchanged.' });
  });
});
