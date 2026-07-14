import React, { useEffect, useMemo, useReducer, useRef, useState } from 'react';
import { Alert, Box, Button, Chip, LinearProgress, Paper, Skeleton, Stack, TextField, Typography } from '@mui/material';
import FlagRoundedIcon from '@mui/icons-material/FlagRounded';
import CheckCircleRoundedIcon from '@mui/icons-material/CheckCircleRounded';
import WarningAmberRoundedIcon from '@mui/icons-material/WarningAmberRounded';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import { fetchPrimaryGoal, updatePrimaryGoal } from './wealthApi';
import type { FieldProblemResponse, GoalConfigurationUpdate, GoalScenarioKey, PrimaryGoalResponse } from './wealthTypes';
import { formatCompactCrore, formatIndianCurrency, goalErrorFieldKey, progressFill } from './wealthGoalMath';
import WealthGoalChart from './WealthGoalChart';

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

const WealthGoalWorkspace: React.FC<{ onOpenDataImport?: () => void }> = ({ onOpenDataImport }) => {
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
export default WealthGoalWorkspace;
