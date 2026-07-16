import React from 'react';
import {
  Alert,
  Box,
  Button,
  InputAdornment,
  Paper,
  Stack,
  Switch,
  TextField,
  Typography,
} from '@mui/material';
import { formatCrore } from './familyWealthMath';
import type { FamilyPlanDraft } from './FamilyPlanAssumptions';
import type { FamilyPlanResponse, FamilyPlanUpdate } from './wealthTypes';

type Props = {
  data: FamilyPlanResponse;
  draft: FamilyPlanDraft;
  onChange: (draft: FamilyPlanDraft) => void;
  onSave: (payload: FamilyPlanUpdate) => void;
  toUpdate: (draft: FamilyPlanDraft) => FamilyPlanUpdate;
  dirty: boolean;
  disabled: boolean;
  fieldErrors: Partial<Record<string, string>>;
};

type ScenarioDraft = FamilyPlanDraft['scenarios'][number];
type NumericKey = Exclude<keyof ScenarioDraft, 'scenario_key' | 'step_up_enabled'>;

const labels = {
  conservative: 'Conservative',
  expected: 'Expected',
  optimistic: 'Optimistic',
} as const;

const tones = {
  conservative: { border: '#D98A00', bg: '#FFF9ED' },
  expected: { border: '#2563EB', bg: '#F3F7FF' },
  optimistic: { border: '#7357B6', bg: '#F8F5FF' },
} as const;

const rows: Array<{ key: NumericKey; label: string; suffix: string; width: number }> = [
  { key: 'financial_return_pct', label: 'Financial return', suffix: '%', width: 96 },
  { key: 'property_growth_pct', label: 'Property growth', suffix: '%', width: 96 },
  { key: 'monthly_contribution_inr', label: 'Monthly investment', suffix: '₹L/mo', width: 118 },
  { key: 'step_up_pct', label: 'Step-up', suffix: '%', width: 96 },
  { key: 'contribution_stop_age', label: 'Contribution stop', suffix: 'age', width: 104 },
];

export const FamilyScenarioMatrix: React.FC<Props> = ({
  data,
  draft,
  onChange,
  onSave,
  toUpdate,
  dirty,
  disabled,
  fieldErrors,
}) => {
  const change = (index: number, key: keyof ScenarioDraft, value: string | boolean) =>
    onChange({
      ...draft,
      scenarios: draft.scenarios.map((scenario, at) =>
        at === index ? { ...scenario, [key]: value } : scenario,
      ),
    });

  const displayValue = (scenario: ScenarioDraft, key: NumericKey) =>
    key === 'monthly_contribution_inr'
      ? String(Number(scenario[key] || 0) / 100_000)
      : String(scenario[key]);

  const storeValue = (key: NumericKey, value: string) =>
    key === 'monthly_contribution_inr'
      ? value === '' ? '' : String(Number(value) * 100_000)
      : value;

  const input = (scenario: ScenarioDraft, index: number, row: typeof rows[number]) => {
    const error = fieldErrors[`scenarios.${index}.${row.key}`];
    return (
      <TextField
        key={`${scenario.scenario_key}-${row.key}`}
        data-testid="compact-scenario-input"
        size="small"
        hiddenLabel
        type="number"
        value={displayValue(scenario, row.key)}
        disabled={disabled || (row.key === 'step_up_pct' && !scenario.step_up_enabled)}
        onChange={(event) => change(index, row.key, storeValue(row.key, event.target.value))}
        error={Boolean(error)}
        helperText={error}
        inputProps={{
          'aria-label': `${labels[scenario.scenario_key]} ${row.label}`,
          step: row.key === 'contribution_stop_age' ? 1 : 0.1,
        }}
        InputProps={{ endAdornment: <InputAdornment position="end">{row.suffix}</InputAdornment> }}
        sx={{
          width: row.width,
          '& .MuiInputBase-root': { height: 36, bgcolor: '#fff' },
          '& .MuiFormHelperText-root': { mx: 0, maxWidth: row.width },
        }}
      />
    );
  };

  const projectionFor = (scenario: ScenarioDraft) =>
    data.scenario_projections.find((item) => item.settings.scenario_key === scenario.scenario_key);

  const result = (scenario: ScenarioDraft) => {
    const projection = projectionFor(scenario);
    const milestone = projection?.december_2029_milestone;
    return (
      <Box sx={{ p: 1.25, borderRadius: 2, bgcolor: tones[scenario.scenario_key].bg, minWidth: 0 }}>
        <Typography variant="caption" color="text.secondary">Ending net worth · age {data.projection_end_age}</Typography>
        <Typography fontWeight={900}>{formatCrore(projection?.ending_total_net_worth_inr)}</Typography>
        <Typography variant="caption" color="text.secondary">₹15 Cr · Dec 2029</Typography>
        <Typography fontWeight={800} color={milestone?.on_track ? 'success.main' : 'error.main'}>
          {milestone?.on_track ? 'On track' : 'Shortfall'} · {formatCrore(milestone?.projected_value_inr)}
        </Typography>
      </Box>
    );
  };

  return (
    <Box component="section" aria-labelledby="scenario-matrix-title" sx={{ minWidth: 0, maxWidth: '100%' }}>
      <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ sm: 'center' }} gap={1} mb={1.25}>
        <Box>
          <Typography id="scenario-matrix-title" variant="h5" fontWeight={900}>Scenario comparison</Typography>
          <Typography variant="body2" color="text.secondary">Tune assumptions and recalculate the chart above.</Typography>
        </Box>
        <Button size="small" variant="contained" disabled={!dirty || disabled} onClick={() => onSave(toUpdate(draft))}>
          {disabled ? 'Saving…' : 'Save & recalculate'}
        </Button>
      </Stack>

      {dirty && <Alert severity="warning" sx={{ mb: 1 }}>Draft values are not yet reflected in the calculated results.</Alert>}

      <Box
        data-testid="scenario-desktop-matrix"
        sx={{
          display: { xs: 'none', md: 'grid' },
          gridTemplateColumns: '170px repeat(3,minmax(180px,1fr))',
          columnGap: 1.5,
          rowGap: 1,
          alignItems: 'center',
        }}
      >
        <Box />
        {draft.scenarios.map((scenario) => (
          <Typography key={scenario.scenario_key} fontWeight={900} sx={{ borderTop: `3px solid ${tones[scenario.scenario_key].border}`, pt: .75 }}>
            {labels[scenario.scenario_key]}
          </Typography>
        ))}
        {rows.slice(0, 3).map((row) => (
          <React.Fragment key={row.key}>
            <Typography variant="body2" fontWeight={750}>{row.label}</Typography>
            {draft.scenarios.map((scenario, index) => input(scenario, index, row))}
          </React.Fragment>
        ))}
        <Typography variant="body2" fontWeight={750}>Annual step-up</Typography>
        {draft.scenarios.map((scenario, index) => (
          <Stack key={`${scenario.scenario_key}-step-up`} direction="row" alignItems="center" spacing={.5}>
            <Switch size="small" checked={scenario.step_up_enabled} disabled={disabled} inputProps={{ 'aria-label': `${labels[scenario.scenario_key]} annual step-up` }} onChange={(event) => change(index, 'step_up_enabled', event.target.checked)} />
            {input(scenario, index, rows[3])}
          </Stack>
        ))}
        <Typography variant="body2" fontWeight={750}>{rows[4].label}</Typography>
        {draft.scenarios.map((scenario, index) => input(scenario, index, rows[4]))}
        <Typography variant="body2" fontWeight={750}>Projected result</Typography>
        {draft.scenarios.map((scenario) => <React.Fragment key={`${scenario.scenario_key}-result`}>{result(scenario)}</React.Fragment>)}
      </Box>

      <Stack data-testid="scenario-mobile-cards" spacing={1.25} sx={{ display: { xs: 'flex', md: 'none' } }}>
        {draft.scenarios.map((scenario, index) => (
          <Paper key={scenario.scenario_key} variant="outlined" sx={{ p: 1.5, borderTop: `3px solid ${tones[scenario.scenario_key].border}`, minWidth: 0 }}>
            <Typography fontWeight={900} mb={1}>{labels[scenario.scenario_key]}</Typography>
            <Box sx={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 1, alignItems: 'center' }}>
              {rows.slice(0, 3).map((row) => (
                <React.Fragment key={row.key}>
                  <Typography variant="body2" fontWeight={700}>{row.label}</Typography>
                  {input(scenario, index, row)}
                </React.Fragment>
              ))}
              <Typography variant="body2" fontWeight={700}>Annual step-up</Typography>
              <Stack direction="row" alignItems="center" spacing={.5}>
                <Switch size="small" checked={scenario.step_up_enabled} disabled={disabled} inputProps={{ 'aria-label': `${labels[scenario.scenario_key]} annual step-up` }} onChange={(event) => change(index, 'step_up_enabled', event.target.checked)} />
                {input(scenario, index, rows[3])}
              </Stack>
              <Typography variant="body2" fontWeight={700}>{rows[4].label}</Typography>
              {input(scenario, index, rows[4])}
            </Box>
            <Box mt={1.25}>{result(scenario)}</Box>
          </Paper>
        ))}
      </Stack>
    </Box>
  );
};
