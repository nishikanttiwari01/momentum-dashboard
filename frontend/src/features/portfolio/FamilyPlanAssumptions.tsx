import React from 'react';
import { Alert, Box, Checkbox, FormControlLabel, Stack, Switch, TextField, Typography } from '@mui/material';
import type { FamilyPlanResponse, FamilyPlanUpdate, FamilyScenarioKey, LinkedGoalSettings } from './wealthTypes';

type NumericDraft<T> = { [K in keyof T]: T[K] extends number ? string : T[K] };
export type FamilyPlanDraft = {
  birth_year: string;
  birth_month: string;
  projection_end_age: string;
  primary_goal: { name: string; target_amount_inr: string; deadline: string };
  assumptions: NumericDraft<FamilyPlanResponse['assumptions']>;
  scenarios: { scenario_key: FamilyScenarioKey; financial_return_pct: string; property_growth_pct: string; monthly_contribution_inr: string; step_up_enabled: boolean; step_up_pct: string; contribution_stop_age: string }[];
  goals: NumericDraft<LinkedGoalSettings>[];
};

const numeric = (value: string) => Number(value);
export function familyPlanDraftFromResponse(plan: FamilyPlanResponse): FamilyPlanDraft {
  const stringifyNumbers = <T extends Record<string, unknown>>(item: T) => Object.fromEntries(
    Object.entries(item).map(([key, value]) => [key, typeof value === 'number' ? String(value) : value]),
  ) as NumericDraft<T>;
  return {
    birth_year: String(plan.birth_year), birth_month: String(plan.birth_month), projection_end_age: String(plan.projection_end_age),
    primary_goal: { name: plan.primary_goal.goal.name, target_amount_inr: String(plan.primary_goal.goal.target_amount_inr), deadline: plan.primary_goal.goal.deadline },
    assumptions: stringifyNumbers(plan.assumptions),
    scenarios: plan.scenario_projections.map(({ settings }) => ({ ...settings, financial_return_pct: String(settings.financial_return_pct), property_growth_pct: String(settings.property_growth_pct), monthly_contribution_inr: String(settings.monthly_contribution_inr), step_up_pct: String(settings.step_up_pct), contribution_stop_age: String(settings.contribution_stop_age) })),
    goals: plan.goals.map(stringifyNumbers),
  };
}

export function familyPlanUpdateFromDraft(draft: FamilyPlanDraft): FamilyPlanUpdate {
  return {
    birth_year: numeric(draft.birth_year), birth_month: numeric(draft.birth_month), projection_end_age: numeric(draft.projection_end_age),
    primary_goal: { ...draft.primary_goal, target_amount_inr: numeric(draft.primary_goal.target_amount_inr) },
    assumptions: {
      ...draft.assumptions,
      monthly_contribution_inr: numeric(draft.assumptions.monthly_contribution_inr),
      contribution_step_up_pct: numeric(draft.assumptions.contribution_step_up_pct),
      monthly_rent_inr: numeric(draft.assumptions.monthly_rent_inr),
      rent_growth_pct: numeric(draft.assumptions.rent_growth_pct),
      property_growth_pct: numeric(draft.assumptions.property_growth_pct),
      withdrawal_rate_pct: numeric(draft.assumptions.withdrawal_rate_pct),
      amber_margin_pct: numeric(draft.assumptions.amber_margin_pct),
    },
    scenarios: draft.scenarios.map((item) => ({ ...item, financial_return_pct: numeric(item.financial_return_pct), property_growth_pct: numeric(item.property_growth_pct), monthly_contribution_inr: numeric(item.monthly_contribution_inr), step_up_pct: numeric(item.step_up_pct), contribution_stop_age: numeric(item.contribution_stop_age) })),
    goals: draft.goals.map((goal) => ({
      ...goal,
      current_value_amount_inr: numeric(goal.current_value_amount_inr), inflation_pct: numeric(goal.inflation_pct),
      priority: numeric(goal.priority), display_order: numeric(goal.display_order),
    })),
  };
}

type Props = { value: FamilyPlanDraft; onChange: (value: FamilyPlanDraft) => void; fieldErrors: Partial<Record<string, string>>; disabled: boolean; dirty?: boolean };
const input = { min: 0, step: 0.1 };
export const FamilyPlanAssumptions: React.FC<Props> = ({ value, onChange, fieldErrors, disabled, dirty = false }) => {
  const setPrimary = (key: keyof FamilyPlanDraft['primary_goal'], next: string) => onChange({ ...value, primary_goal: { ...value.primary_goal, [key]: next } });
  const setAssumption = (key: keyof FamilyPlanDraft['assumptions'], next: string | boolean) => onChange({ ...value, assumptions: { ...value.assumptions, [key]: next } });
  const setGoal = (index: number, key: keyof FamilyPlanDraft['goals'][number], next: string | boolean) => onChange({ ...value, goals: value.goals.map((item, at) => at === index ? { ...item, [key]: next } : item) });
  const assumptionField = (key: keyof FamilyPlanDraft['assumptions'], label: string, options: Record<string, unknown> = {}) => <TextField fullWidth disabled={disabled} label={label} type="number" value={String(value.assumptions[key])} onChange={(event) => setAssumption(key, event.target.value)} inputProps={input} error={Boolean(fieldErrors[`assumptions.${key}`])} helperText={fieldErrors[`assumptions.${key}`]} {...options} />;
  return <Stack spacing={2.5} sx={{ width: { xs: 'min(92vw, 560px)', sm: 560 }, maxWidth: '100%', p: { xs: 2, sm: 3 }, overflowX: 'hidden' }}>
    <Box><Typography variant="overline" color="primary" fontWeight={900}>Planning controls</Typography><Typography variant="h5" fontWeight={900}>Family plan assumptions</Typography><Typography color="text.secondary">Adjust the inputs, review the draft, then save to calculate a new runway.</Typography></Box>
    {dirty && <Alert severity="warning"><b>Draft assumptions.</b> Charts still show the last saved calculation until you save changes.</Alert>}
    <Box component="section"><Typography variant="h6" fontWeight={850} mb={1}>Primary goal</Typography><Stack spacing={1.5}><TextField fullWidth disabled={disabled} label="Goal name" value={value.primary_goal.name} onChange={(event) => setPrimary('name', event.target.value)} error={Boolean(fieldErrors['primary_goal.name'])} helperText={fieldErrors['primary_goal.name']} /><TextField fullWidth disabled={disabled} label="Target amount" type="number" value={value.primary_goal.target_amount_inr} onChange={(event) => setPrimary('target_amount_inr', event.target.value)} inputProps={input} error={Boolean(fieldErrors['primary_goal.target_amount_inr'])} helperText={fieldErrors['primary_goal.target_amount_inr']} /><TextField fullWidth disabled={disabled} label="Target deadline" type="date" value={value.primary_goal.deadline} onChange={(event) => setPrimary('deadline', event.target.value)} InputLabelProps={{ shrink: true }} error={Boolean(fieldErrors['primary_goal.deadline'])} helperText={fieldErrors['primary_goal.deadline']} /></Stack></Box>
    <Box component="section"><Typography variant="h6" fontWeight={850} mb={1}>Contributions</Typography><Stack spacing={1.5}>{assumptionField('monthly_contribution_inr', 'Monthly investment')}<FormControlLabel control={<Checkbox disabled={disabled} checked={value.assumptions.contribution_step_up_enabled} onChange={(event) => setAssumption('contribution_step_up_enabled', event.target.checked)} />} label="Annual contribution step-up" />{assumptionField('contribution_step_up_pct', 'Annual step-up (%)', { disabled: disabled || !value.assumptions.contribution_step_up_enabled })}</Stack></Box>
    <Box component="section"><Typography variant="h6" fontWeight={850} mb={1}>Lifetime horizon</Typography><Stack spacing={1.5}><TextField label="Birth year" type="number" value={value.birth_year} onChange={(e) => onChange({...value,birth_year:e.target.value})}/><TextField label="Birth month" type="number" value={value.birth_month} onChange={(e) => onChange({...value,birth_month:e.target.value})}/><TextField label="Projection end age" type="number" value={value.projection_end_age} onChange={(e) => onChange({...value,projection_end_age:e.target.value})}/></Stack></Box>
    <Box component="section"><Typography variant="h6" fontWeight={850} mb={1}>Rent</Typography><Stack spacing={1.5}>{assumptionField('monthly_rent_inr', 'Monthly rent')}{assumptionField('rent_growth_pct', 'Annual rent growth (%)')}<TextField fullWidth disabled={disabled} label="Reinvest rent until" type="date" value={value.assumptions.reinvest_rent_until} onChange={(event) => setAssumption('reinvest_rent_until', event.target.value)} InputLabelProps={{ shrink: true }} error={Boolean(fieldErrors['assumptions.reinvest_rent_until'])} helperText={fieldErrors['assumptions.reinvest_rent_until']} /></Stack></Box>
    <Box component="section"><Typography variant="h6" fontWeight={850} mb={1}>Income safety</Typography><Stack spacing={1.5}>{assumptionField('withdrawal_rate_pct', 'Withdrawal rate (%)')}{assumptionField('amber_margin_pct', 'Amber safety margin (%)')}</Stack></Box>
    <Box component="section"><Typography variant="h6" fontWeight={850} mb={1}>Linked family goals</Typography><Stack spacing={2}>{value.goals.map((goal, index) => <Box key={goal.goal_key} sx={{ border: '1px solid #DCE7F2', borderRadius: 2, p: 1.5 }}><Stack spacing={1.25}><FormControlLabel control={<Switch disabled={disabled} checked={goal.enabled} onChange={(event) => setGoal(index, 'enabled', event.target.checked)} />} label={goal.name} /><TextField fullWidth disabled={disabled} label="Goal name" value={goal.name} onChange={(event) => setGoal(index, 'name', event.target.value)} error={Boolean(fieldErrors[`goals.${index}.name`])} helperText={fieldErrors[`goals.${index}.name`]} /><TextField fullWidth disabled={disabled} label="Current cost / income target" type="number" value={goal.current_value_amount_inr} onChange={(event) => setGoal(index, 'current_value_amount_inr', event.target.value)} inputProps={input} error={Boolean(fieldErrors[`goals.${index}.current_value_amount_inr`])} helperText={fieldErrors[`goals.${index}.current_value_amount_inr`]} /><TextField fullWidth disabled={disabled} label="Target date" type="date" value={goal.target_date} onChange={(event) => setGoal(index, 'target_date', event.target.value)} InputLabelProps={{ shrink: true }} error={Boolean(fieldErrors[`goals.${index}.target_date`])} helperText={fieldErrors[`goals.${index}.target_date`]} /><TextField fullWidth disabled={disabled} label="Inflation (%)" type="number" value={goal.inflation_pct} onChange={(event) => setGoal(index, 'inflation_pct', event.target.value)} inputProps={input} error={Boolean(fieldErrors[`goals.${index}.inflation_pct`])} helperText={fieldErrors[`goals.${index}.inflation_pct`]} /><TextField fullWidth disabled={disabled} label="Funding priority" type="number" value={goal.priority} onChange={(event) => setGoal(index, 'priority', event.target.value)} inputProps={{ min: 1, max: 100 }} error={Boolean(fieldErrors[`goals.${index}.priority`])} helperText={fieldErrors[`goals.${index}.priority`]} /></Stack></Box>)}</Stack></Box>
  </Stack>;
};
