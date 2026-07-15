import React, { useEffect, useMemo, useReducer, useRef, useState } from 'react';
import { Alert, Box, Button, Chip, Drawer, LinearProgress, Paper, Skeleton, Stack, TextField, Typography } from '@mui/material';
import FlagRoundedIcon from '@mui/icons-material/FlagRounded';
import CheckCircleRoundedIcon from '@mui/icons-material/CheckCircleRounded';
import WarningAmberRoundedIcon from '@mui/icons-material/WarningAmberRounded';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import { fetchFamilyPlan, fetchPrimaryGoal, restoreFamilyPlanDefaults, updateFamilyPlan, updatePrimaryGoal } from './wealthApi';
import type { FamilyPlanResponse, FamilyPlanUpdate, FieldProblemResponse, GoalConfigurationUpdate, GoalScenarioKey, PrimaryGoalResponse } from './wealthTypes';
import { formatCompactCrore, formatIndianCurrency, goalErrorFieldKey, progressFill } from './wealthGoalMath';
import { familyPlanProblemField, formatCrore } from './familyWealthMath';
import WealthGoalChart from './WealthGoalChart';
import { FamilyPlanAssumptions, familyPlanDraftFromResponse, familyPlanUpdateFromDraft, type FamilyPlanDraft } from './FamilyPlanAssumptions';
import { FamilyWealthRunwayChart } from './FamilyWealthRunwayChart';
import { FamilyGoalCards } from './FamilyGoalCards';
import { PassiveIncomePanel } from './PassiveIncomePanel';

type ScenarioForm = { scenario_key: GoalScenarioKey; annual_return_pct: string; monthly_contribution: string };
export type GoalForm = { name: string; target: string; deadline: string; scenarios: ScenarioForm[] };
type FieldErrors = Partial<Record<string, string>>;
export type GoalFormChange =
  | { type: 'field'; field: 'target' | 'deadline'; value: string }
  | { type: 'scenario'; index: number; field: 'annual_return_pct' | 'monthly_contribution'; value: string }
  | { type: 'restore' };
export type GoalFormState = { accepted: GoalForm; draft: GoalForm; dirty: boolean; saved: boolean };
export type GoalFormAction =
  | { type: 'change'; change: GoalFormChange }
  | { type: 'serverSync'; form: GoalForm }
  | { type: 'saveSuccess'; form: GoalForm };
export type GoalSaveStatus = { saved: boolean; error: { message: string; payload: GoalConfigurationUpdate } | null };

export const DEFAULT_GOAL_FORM: GoalForm = { name: '₹15 Cr by 2029', target: '150000000', deadline: '2029-12-31', scenarios: [
  { scenario_key: 'conservative', annual_return_pct: '7', monthly_contribution: '0' },
  { scenario_key: 'expected', annual_return_pct: '10', monthly_contribution: '0' },
  { scenario_key: 'optimistic', annual_return_pct: '13', monthly_contribution: '0' },
] };

export function goalFormFromResponse(data: PrimaryGoalResponse): GoalForm { return { name: data.goal.name, target: String(data.goal.target_amount_inr), deadline: data.goal.deadline, scenarios: data.scenario_projections.map(({ settings }) => ({ scenario_key: settings.scenario_key, annual_return_pct: String(settings.annual_return_pct), monthly_contribution: String(settings.monthly_contribution_inr) })) }; }
export function goalUpdateFromForm(form: GoalForm): GoalConfigurationUpdate { return { goal: { name: form.name, target_amount_inr: Number(form.target), deadline: form.deadline }, scenarios: form.scenarios.map((item) => ({ scenario_key: item.scenario_key, annual_return_pct: Number(item.annual_return_pct), monthly_contribution_inr: Number(item.monthly_contribution) })) }; }
export function applyGoalFormChange(form: GoalForm, change: GoalFormChange): GoalForm {
  if (change.type === 'restore') return structuredClone(DEFAULT_GOAL_FORM);
  if (change.type === 'field') return { ...form, [change.field]: change.value };
  return { ...form, scenarios: form.scenarios.map((item, index) => index === change.index ? { ...item, [change.field]: change.value } : item) };
}
const formsEqual = (left: GoalForm, right: GoalForm) => JSON.stringify(left) === JSON.stringify(right);
export function createGoalFormState(accepted: GoalForm, draft: GoalForm = accepted, saved = false): GoalFormState {
  return { accepted, draft, dirty: !formsEqual(draft, accepted), saved };
}
export function goalFormReducer(state: GoalFormState, action: GoalFormAction): GoalFormState {
  if (action.type === 'change') {
    const draft = applyGoalFormChange(state.draft, action.change);
    return { ...state, draft, dirty: !formsEqual(draft, state.accepted), saved: false };
  }
  if (action.type === 'serverSync') {
    const draft = state.dirty ? state.draft : action.form;
    return { ...state, accepted: action.form, draft, dirty: !formsEqual(draft, action.form) };
  }
  return { accepted: action.form, draft: action.form, dirty: false, saved: true };
}
export function goalSubmissionFromState(state: GoalFormState): GoalConfigurationUpdate { return goalUpdateFromForm(state.draft); }
export function isGoalSaveDisabled(state: Pick<GoalFormState, 'dirty'>, isSaving: boolean): boolean { return !state.dirty || isSaving; }
export function retryGoalSave(error: { payload: GoalConfigurationUpdate } | null, submit: (payload: GoalConfigurationUpdate) => void): void { if (error) submit(error.payload); }
export function clearGoalSaveFeedback(): GoalSaveStatus { return { saved: false, error: null }; }
export function applyUserGoalFormChange(change: GoalFormChange, onDraftChange: (() => void) | undefined, dispatch: (action: GoalFormAction) => void): void {
  onDraftChange?.();
  dispatch({ type: 'change', change });
}

export const wealthGoalQueryOptions = { queryKey: ['wealth-primary-goal'] as const, queryFn: fetchPrimaryGoal, retry: 1 };
export const familyPlanQueryOptions = { queryKey: ['wealth-family-plan'] as const, queryFn: fetchFamilyPlan, retry: 1 };
type GoalCacheClient = Pick<ReturnType<typeof useQueryClient>, 'setQueryData' | 'invalidateQueries'>;
export function applyGoalMutationSuccess(client: GoalCacheClient, next: PrimaryGoalResponse) {
  client.setQueryData(wealthGoalQueryOptions.queryKey, next);
  void client.invalidateQueries({ queryKey: wealthGoalQueryOptions.queryKey });
}

const cardSx = { borderRadius: 3, borderColor: '#DDE6F0', boxShadow: '0 12px 32px rgba(22,34,58,.055)' };
const completion = (value: string | null) => value ?? 'Beyond projection horizon';
export const formatGoalPercentage = (value: number) => Number(value.toFixed(2)).toString();

function Metric({ label, value }: { label: string; value: string }) { return <Paper variant="outlined" sx={{ ...cardSx, p: 1.75 }}><Typography variant="caption" color="text.secondary">{label}</Typography><Typography variant="h6" fontWeight={850}>{value}</Typography></Paper>; }

export function EmptyWealthGoalAlert({ onOpenDataImport, disabled = false }: { onOpenDataImport?: () => void; disabled?: boolean }) { return (
  <Alert severity="info" action={<Button color="inherit" onClick={onOpenDataImport} disabled={disabled || !onOpenDataImport}>Import workbook</Button>}>
    Import investment.xlsx to add your current wealth; goal settings remain editable.
  </Alert>
); }

export const WealthGoalWorkspaceView: React.FC<{ data: PrimaryGoalResponse; onSave: (update: GoalConfigurationUpdate) => void; isSaving: boolean; initialForm?: GoalForm; fieldErrors?: FieldErrors; saved?: boolean; saveError?: string | null; onRetrySave?: () => void; onOpenDataImport?: () => void; onDraftChange?: () => void }> = ({ data, onSave, isSaving, initialForm, fieldErrors = {}, saved: savedProp, saveError = null, onRetrySave, onOpenDataImport, onDraftChange }) => {
  const responseForm = useMemo(() => goalFormFromResponse(data), [data]);
  const [formState, dispatchForm] = useReducer(
    goalFormReducer,
    { accepted: responseForm, draft: initialForm ?? responseForm, saved: Boolean(savedProp) },
    (seed) => createGoalFormState(seed.accepted, seed.draft, seed.saved),
  );
  const previousSaved = useRef(savedProp);
  useEffect(() => { if (!initialForm) dispatchForm({ type: 'serverSync', form: responseForm }); }, [responseForm, initialForm]);
  useEffect(() => {
    if (savedProp && !previousSaved.current) dispatchForm({ type: 'saveSuccess', form: responseForm });
    previousSaved.current = savedProp;
  }, [savedProp, responseForm]);
  const form = formState.draft;
  const dirty = formState.dirty;
  const saved = formState.saved;
  const changeForm = (change: GoalFormChange) => applyUserGoalFormChange(change, onDraftChange, dispatchForm);
  const achieved = data.achieved_pct;
  const achievedText = achieved == null ? null : formatGoalPercentage(achieved);
  const expected = data.scenario_projections.find((item) => item.settings.scenario_key === 'expected');
  return <Stack data-testid="wealth-goal-workspace" spacing={2.25}>
    {data.data_health === 'warning' && <Alert severity="warning">Attention needed — projections use the latest available portfolio snapshot.</Alert>}
    {data.data_health === 'empty' && <EmptyWealthGoalAlert onOpenDataImport={onOpenDataImport} disabled={isSaving} />}
    <Paper variant="outlined" sx={{ ...cardSx, p: { xs: 2, md: 2.5 }, overflow: 'hidden' }}>
      <Stack direction="row" alignItems="center" spacing={1}><FlagRoundedIcon color="primary" /><Typography variant="overline" fontWeight={900}>Finish line</Typography></Stack>
      <Typography variant="h4" fontWeight={900}>{data.goal.name}</Typography>
      <Typography color="text.secondary">Target {formatCompactCrore(data.goal.target_amount_inr)} · deadline {data.goal.deadline} · current {formatCompactCrore(data.current_value_inr)}</Typography>
      <Box sx={{ mt: 2, p: 0.6, bgcolor: '#E8EEF5', borderRadius: 8 }} aria-label={`Goal progress ${achievedText == null ? 'unavailable' : `${achievedText}%`}`}>
        <LinearProgress data-progress-fill={progressFill(achieved ?? 0)} variant="determinate" value={progressFill(achieved ?? 0)} sx={{ height: 16, borderRadius: 8, '& .MuiLinearProgress-bar': { borderRadius: 8, background: 'repeating-linear-gradient(90deg,#2563EB 0,#2563EB 28px,#3B82F6 28px,#3B82F6 31px)' } }} />
      </Box>
      <Stack direction="row" justifyContent="space-between" mt={1}><Typography fontWeight={800}>{achievedText == null ? 'Progress unavailable' : `${achievedText}% achieved`}</Typography><Typography>Remaining {formatCompactCrore(data.remaining_inr)}</Typography></Stack>
    </Paper>
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr 1fr', lg: 'repeat(4,1fr)' }, gap: 1.5 }}>
      <Metric label="Remaining" value={formatCompactCrore(data.remaining_inr)} />
      <Metric label="Required monthly investment" value={formatIndianCurrency(data.required_monthly_contribution_inr)} />
      <Metric label="Expected deadline value" value={formatCompactCrore(expected?.projected_deadline_value_inr ?? null)} />
      <Metric label="Expected projected completion date" value={completion(expected?.projected_completion_date ?? null)} />
    </Box>
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: 'minmax(0,1fr)', lg: 'minmax(0,1.7fr) minmax(300px,.8fr)' }, gap: 2 }}>
      <Paper variant="outlined" sx={{ ...cardSx, p: 2, minWidth: 0 }}><Typography variant="h6" fontWeight={850}>Paths to the finish line</Typography><WealthGoalChart data={data} /></Paper>
      <Paper component="form" variant="outlined" sx={{ ...cardSx, p: 2 }} onSubmit={(event) => { event.preventDefault(); onSave(goalUpdateFromForm(form)); }}>
        <Stack spacing={1.5}><Stack direction="row" justifyContent="space-between"><Typography variant="h6" fontWeight={850}>Configuration</Typography>{dirty && <Chip size="small" label="Unsaved changes" color="warning" variant="outlined" />}</Stack>
          <TextField disabled={isSaving} label="Target amount" type="number" value={form.target} onChange={(e) => changeForm({ type: 'field', field: 'target', value: e.target.value })} inputProps={{ min: 0 }} error={Boolean(fieldErrors.target)} helperText={fieldErrors.target} />
          <TextField disabled={isSaving} label="Deadline" type="date" value={form.deadline} onChange={(e) => changeForm({ type: 'field', field: 'deadline', value: e.target.value })} InputLabelProps={{ shrink: true }} error={Boolean(fieldErrors.deadline)} helperText={fieldErrors.deadline} />
          {form.scenarios.map((item, index) => <Box key={item.scenario_key}><Typography fontWeight={800} textTransform="capitalize" mb={1}>{item.scenario_key}</Typography><Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
            <TextField disabled={isSaving} fullWidth label={`${item.scenario_key[0].toUpperCase() + item.scenario_key.slice(1)} annual return`} type="number" value={item.annual_return_pct} onChange={(e) => changeForm({ type: 'scenario', index, field: 'annual_return_pct', value: e.target.value })} inputProps={{ min: -25, max: 50, step: .1 }} error={Boolean(fieldErrors[`scenarios.${index}.annual_return_pct`])} helperText={fieldErrors[`scenarios.${index}.annual_return_pct`]} />
            <TextField disabled={isSaving} fullWidth label={`${item.scenario_key[0].toUpperCase() + item.scenario_key.slice(1)} Monthly contribution`} type="number" value={item.monthly_contribution} onChange={(e) => changeForm({ type: 'scenario', index, field: 'monthly_contribution', value: e.target.value })} inputProps={{ min: 0 }} error={Boolean(fieldErrors[`scenarios.${index}.monthly_contribution`])} helperText={fieldErrors[`scenarios.${index}.monthly_contribution`]} />
          </Stack></Box>)}
          {saved && <Alert severity="success">Goal settings saved</Alert>}
          {saveError && <Alert severity="error" action={onRetrySave && <Button color="inherit" disabled={isSaving} onClick={onRetrySave}>Retry</Button>}>{saveError}</Alert>}
          <Stack direction="row" spacing={1}><Button type="submit" variant="contained" disabled={isGoalSaveDisabled(formState, isSaving)}>{isSaving ? 'Saving…' : 'Save changes'}</Button><Button type="button" disabled={isSaving} onClick={() => changeForm({ type: 'restore' })}>Restore defaults</Button></Stack>
        </Stack>
      </Paper>
    </Box>
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(3,1fr)' }, gap: 1.5 }}>{data.scenario_projections.map((scenario) => <Paper key={scenario.settings.scenario_key} variant="outlined" sx={{ ...cardSx, p: 2, borderTop: `4px solid ${{ conservative: '#F59E0B', expected: '#2563EB', optimistic: '#059669' }[scenario.settings.scenario_key]}` }}>
      <Typography variant="h6" fontWeight={900} textTransform="capitalize">{scenario.settings.scenario_key}</Typography>
      <Stack direction="row" alignItems="center" spacing={.75}>{scenario.on_track ? <CheckCircleRoundedIcon color="success" /> : <WarningAmberRoundedIcon color="warning" />}<Typography fontWeight={800}>{scenario.on_track == null ? 'Track status unavailable' : scenario.on_track ? 'On track' : 'Needs attention'}</Typography></Stack>
      <Typography>Deadline value <b>{formatCompactCrore(scenario.projected_deadline_value_inr)}</b></Typography><Typography>Surplus/shortfall <b>{formatCompactCrore(scenario.surplus_or_shortfall_inr)}</b></Typography>
      <Typography>Monthly contribution <b>{formatIndianCurrency(scenario.settings.monthly_contribution_inr)}</b></Typography><Typography>Annual return <b>{scenario.settings.annual_return_pct}%</b></Typography><Typography>Completion <b>{completion(scenario.projected_completion_date)}</b></Typography>
    </Paper>)}</Box>
  </Stack>;
};

export function classifyGoalSaveError(error: unknown): { kind: 'fields'; errors: FieldErrors } | { kind: 'form'; message: string } {
  const errors: FieldErrors = {};
  if (axios.isAxiosError<FieldProblemResponse>(error) && error.response?.status === 422) {
    error.response.data?.errors?.forEach((problem) => { const key = goalErrorFieldKey(problem.loc); if (key) errors[key] = problem.msg; });
    if (Object.keys(errors).length) return { kind: 'fields', errors };
  }
  return { kind: 'form', message: 'Could not save goal settings. Please try again.' };
}

export const WealthGoalLoading = () => <Paper data-testid="wealth-goal-workspace" variant="outlined" sx={{ ...cardSx, minHeight: 640, p: 2 }}><Skeleton height={90} /><Skeleton variant="rounded" height={220} /><Skeleton height={160} /></Paper>;
export function WealthGoalError({ retry }: { retry: () => void }) { return <Alert data-testid="wealth-goal-workspace" severity="error" action={<Button color="inherit" onClick={retry}>Retry</Button>}>We couldn’t load your wealth goal. No estimates are shown until the data is available.</Alert>; }

export function classifyFamilyPlanSaveError(error: unknown): { kind: 'fields'; errors: FieldErrors } | { kind: 'form'; message: string } {
  const errors: FieldErrors = {};
  if (axios.isAxiosError<FieldProblemResponse>(error) && error.response?.status === 422) {
    error.response.data?.errors?.forEach((problem) => { const key = familyPlanProblemField(problem.loc); if (key) errors[key] = problem.msg; });
    if (Object.keys(errors).length) return { kind: 'fields', errors };
  }
  return { kind: 'form', message: 'Could not calculate the updated family plan. Your last saved plan is unchanged.' };
}

const familyDraftEqual = (left: FamilyPlanDraft, right: FamilyPlanDraft) => JSON.stringify(left) === JSON.stringify(right);
export type FamilyPlanFormState = { accepted: FamilyPlanDraft | null; draft: FamilyPlanDraft | null };
export type FamilyPlanFormAction = { type: 'load'; value: FamilyPlanDraft } | { type: 'edit'; value: FamilyPlanDraft } | { type: 'saved'; value: FamilyPlanDraft };
export function familyPlanFormReducer(state: FamilyPlanFormState, action: FamilyPlanFormAction): FamilyPlanFormState {
  if (action.type === 'edit') return { ...state, draft: action.value };
  if (action.type === 'saved') return { accepted: action.value, draft: action.value };
  const dirty = state.accepted && state.draft && !familyDraftEqual(state.accepted, state.draft);
  return { accepted: action.value, draft: dirty ? state.draft : action.value };
}
const scenarioTone = { conservative: '#D98A00', expected: '#2563EB', optimistic: '#7357B6' } as const;

export const FamilyPlanWorkspaceView: React.FC<{
  data: FamilyPlanResponse; draft: FamilyPlanDraft; onDraftChange: (draft: FamilyPlanDraft) => void;
  onSave: (payload: FamilyPlanUpdate) => void; onRestore: () => void; isSaving: boolean; fieldErrors?: FieldErrors;
  saveError?: string | null; saved?: boolean; onRetry?: () => void; onOpenDataImport?: () => void;
}> = ({ data, draft, onDraftChange, onSave, onRestore, isSaving, fieldErrors = {}, saveError, saved, onRetry, onOpenDataImport }) => {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const accepted = useMemo(() => familyPlanDraftFromResponse(data), [data]);
  const dirty = !familyDraftEqual(draft, accepted);
  const primary = data.primary_goal;
  const achieved = primary.achieved_pct;
  const expected = data.scenario_projections.find(({ settings }) => settings.scenario_key === 'expected') ?? data.scenario_projections[0];
  const passive = expected?.passive_income;
  return <Stack data-testid="wealth-goal-workspace" spacing={2.25} sx={{ minWidth: 0, overflowX: 'hidden' }}>
    {data.data_health === 'warning' && <Alert severity="warning">Attention needed — projections use the latest available portfolio snapshot.</Alert>}
    {data.data_health === 'empty' && <EmptyWealthGoalAlert onOpenDataImport={onOpenDataImport} disabled={isSaving} />}
    <Paper variant="outlined" sx={{ ...cardSx, p: { xs: 2, md: 2.75 }, overflow: 'hidden', background: 'linear-gradient(120deg,#F7FAFF 0%,#FFFFFF 70%)' }}>
      <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" gap={2}>
        <Box><Stack direction="row" alignItems="center" spacing={1}><FlagRoundedIcon color="primary" /><Typography variant="overline" fontWeight={900}>Primary family finish line</Typography></Stack><Typography variant="h4" fontWeight={900}>{primary.goal.name}</Typography><Typography color="text.secondary">Market-value net worth {formatCompactCrore(primary.current_value_inr)} · target {formatCompactCrore(primary.goal.target_amount_inr)} by {primary.goal.deadline.slice(0, 4)}</Typography></Box>
        <Button variant="outlined" onClick={() => setDrawerOpen(true)}>Edit assumptions</Button>
      </Stack>
      <Box sx={{ mt: 2, p: .6, bgcolor: '#E8EEF5', borderRadius: 8 }} aria-label={`Goal progress ${achieved == null ? 'unavailable' : `${formatGoalPercentage(achieved)}%`}`}><LinearProgress variant="determinate" value={progressFill(achieved ?? 0)} sx={{ height: 16, borderRadius: 8, '& .MuiLinearProgress-bar': { borderRadius: 8, bgcolor: '#2563EB' } }} /></Box>
      <Stack direction="row" justifyContent="space-between" mt={1} flexWrap="wrap"><Typography fontWeight={850}>{achieved == null ? 'Progress unavailable' : `${formatGoalPercentage(achieved)}% complete`}</Typography><Typography>Remaining {formatCompactCrore(primary.remaining_inr)}</Typography></Stack>
      {dirty && <Alert severity="warning" sx={{ mt: 2 }}>Draft assumptions are ready to review. The runway below remains the last saved server calculation.</Alert>}
    </Paper>
    <Paper component="section" variant="outlined" sx={{ ...cardSx, p: { xs: 1.5, md: 2.5 }, minWidth: 0 }}><FamilyWealthRunwayChart projections={data.scenario_projections} /></Paper>
    <Box component="section"><Typography variant="h5" fontWeight={900} mb={1.25}>Linked goals</Typography><FamilyGoalCards goals={expected?.goal_health ?? []} linkedGoals={data.goals} /></Box>
    {passive && <PassiveIncomePanel analysis={passive} />}
    <Box component="section"><Typography variant="h5" fontWeight={900} mb={1.25}>Scenario comparison</Typography><Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(3,minmax(0,1fr))' }, gap: 1.5 }}>{data.scenario_projections.map((scenario) => <Paper key={scenario.settings.scenario_key} variant="outlined" sx={{ ...cardSx, p: 2, minWidth: 0, borderTop: `4px solid ${scenarioTone[scenario.settings.scenario_key]}` }}><Typography fontWeight={900} textTransform="capitalize">{scenario.settings.scenario_key}</Typography><Typography variant="h5" fontWeight={900}>{formatCrore(scenario.ending_total_net_worth_inr)}</Typography><Typography color="text.secondary">Projected ending net worth</Typography><Typography mt={1}>Annual return <b>{scenario.settings.annual_return_pct}%</b></Typography>{scenario.first_underfunded_goal_key && <Typography color="error.main">First funding gap: {scenario.first_underfunded_goal_key.replaceAll('_', ' ')}</Typography>}</Paper>)}</Box></Box>
    {saved && <Alert severity="success">Family plan saved and recalculated.</Alert>}
    {saveError && <Alert severity="error" action={onRetry && <Button color="inherit" disabled={isSaving} onClick={onRetry}>Retry</Button>}>{saveError}</Alert>}
    <Drawer anchor="right" open={drawerOpen} onClose={() => !isSaving && setDrawerOpen(false)} PaperProps={{ sx: { maxWidth: '100%' } }}><FamilyPlanAssumptions value={draft} onChange={onDraftChange} fieldErrors={fieldErrors} disabled={isSaving} dirty={dirty} /><Stack direction="row" spacing={1} sx={{ position: 'sticky', bottom: 0, bgcolor: '#fff', borderTop: '1px solid #DCE7F2', p: 2, zIndex: 1 }}><Button variant="contained" disabled={!dirty || isSaving} onClick={() => onSave(familyPlanUpdateFromDraft(draft))}>{isSaving ? 'Saving…' : 'Save and recalculate'}</Button><Button disabled={isSaving} onClick={onRestore}>Restore defaults</Button></Stack></Drawer>
  </Stack>;
};

export const LegacyWealthGoalWorkspace: React.FC<{ onOpenDataImport?: () => void }> = ({ onOpenDataImport }) => {
  const client = useQueryClient();
  const query = useQuery(wealthGoalQueryOptions);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [saveStatus, setSaveStatus] = useState<GoalSaveStatus>(clearGoalSaveFeedback);
  const mutation = useMutation({ mutationFn: updatePrimaryGoal, onSuccess: (next) => { setFieldErrors({}); setSaveStatus({ saved: true, error: null }); applyGoalMutationSuccess(client, next); }, onError: (error, payload) => { const failure = classifyGoalSaveError(error); if (failure.kind === 'fields') { setFieldErrors(failure.errors); setSaveStatus({ saved: false, error: null }); } else { setSaveStatus({ saved: false, error: { message: failure.message, payload } }); } } });
  if (query.isLoading) return <WealthGoalLoading />;
  if (query.isError || !query.data) return <WealthGoalError retry={() => void query.refetch()} />;
  const clearFeedback = () => { setFieldErrors({}); setSaveStatus(clearGoalSaveFeedback()); };
  return <WealthGoalWorkspaceView data={query.data} onSave={(payload) => { clearFeedback(); mutation.mutate(payload); }} isSaving={mutation.isPending} fieldErrors={fieldErrors} saved={saveStatus.saved} saveError={saveStatus.error?.message} onRetrySave={saveStatus.error ? () => retryGoalSave(saveStatus.error, mutation.mutate) : undefined} onOpenDataImport={onOpenDataImport} onDraftChange={clearFeedback} />;
};

const WealthGoalWorkspace: React.FC<{ onOpenDataImport?: () => void }> = ({ onOpenDataImport }) => {
  const client = useQueryClient();
  const query = useQuery(familyPlanQueryOptions);
  const [form, dispatchForm] = useReducer(familyPlanFormReducer, { accepted: null, draft: null });
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [saveStatus, setSaveStatus] = useState<{ saved: boolean; error: { message: string; payload: FamilyPlanUpdate } | null }>({ saved: false, error: null });
  useEffect(() => { if (query.data) dispatchForm({ type: 'load', value: familyPlanDraftFromResponse(query.data) }); }, [query.data]);
  const mutation = useMutation({ mutationFn: updateFamilyPlan, onSuccess: (next) => { client.setQueryData(familyPlanQueryOptions.queryKey, next); dispatchForm({ type: 'saved', value: familyPlanDraftFromResponse(next) }); setFieldErrors({}); setSaveStatus({ saved: true, error: null }); }, onError: (error, payload) => { const failure = classifyFamilyPlanSaveError(error); if (failure.kind === 'fields') { setFieldErrors(failure.errors); setSaveStatus({ saved: false, error: null }); } else setSaveStatus({ saved: false, error: { message: failure.message, payload } }); } });
  const restore = useMutation({ mutationFn: restoreFamilyPlanDefaults, onSuccess: (next) => { client.setQueryData(familyPlanQueryOptions.queryKey, next); dispatchForm({ type: 'saved', value: familyPlanDraftFromResponse(next) }); setFieldErrors({}); setSaveStatus({ saved: true, error: null }); } });
  if (query.isLoading || (query.data && !form.draft)) return <WealthGoalLoading />;
  if (query.isError || !query.data || !form.draft) return <WealthGoalError retry={() => void query.refetch()} />;
  const edit = (next: FamilyPlanDraft) => { dispatchForm({ type: 'edit', value: next }); setFieldErrors({}); setSaveStatus({ saved: false, error: null }); };
  return <FamilyPlanWorkspaceView data={query.data} draft={form.draft} onDraftChange={edit} onSave={(payload) => { setSaveStatus({ saved: false, error: null }); mutation.mutate(payload); }} onRestore={() => { if (window.confirm('Restore all family-plan assumptions and linked goals to defaults?')) restore.mutate(); }} isSaving={mutation.isPending || restore.isPending} fieldErrors={fieldErrors} saved={saveStatus.saved} saveError={saveStatus.error?.message ?? (restore.isError ? 'Could not restore defaults. Your saved plan is unchanged.' : null)} onRetry={saveStatus.error ? () => mutation.mutate(saveStatus.error!.payload) : undefined} onOpenDataImport={onOpenDataImport} />;
};
export default WealthGoalWorkspace;
