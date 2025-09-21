// detail/IndicatorsGrid.tsx
import * as React from 'react';
import { Grid, Stack, Typography, Divider, Tooltip } from '@mui/material';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import { num, pct, relvol, prox52w } from './utils';

type Indicators = {
  rsi14?: number;
  adx14?: number;
  ema_fast?: number;
  ema_fast_value?: number;
  ema_slow?: number;
  ema_slow_value?: number;
  atr_pct?: number;
  relvol20?: number;
  proximity_52w_high_pct?: number;
};

type Props = {
  ind?: Indicators;
  /** Optional hints for tooltips; leave undefined for now (backend can populate later) */
  hints?: Partial<Record<'ema_fast' | 'ema_slow', string>>;
};

/** Label + value row, with optional info icon (only shown if hint provided) */
const Field: React.FC<{ label: string; value: React.ReactNode; hint?: string }> = ({ label, value, hint }) => (
  <Stack direction="row" spacing={1} alignItems="baseline">
    <Stack direction="row" spacing={0.5} alignItems="center" sx={{ width: 180, color: 'text.secondary', flexShrink: 0 }}>
      <Typography variant="body2">{label}:</Typography>
      {hint ? (
        <Tooltip title={hint}>
          <InfoOutlinedIcon sx={{ fontSize: 14, opacity: 0.7 }} />
        </Tooltip>
      ) : null}
    </Stack>
    <Typography variant="body2" sx={{ fontVariantNumeric: 'tabular-nums' }}>
      {value}
    </Typography>
  </Stack>
);

export default function IndicatorsGrid({ ind = {} as Indicators, hints = {} }: Props) {
  return (
    <BoxedSection title="Indicators">
      <Grid container spacing={1.25}>
        <Grid item xs={12} sm={6}>
          <Field label="RSI(14)" value={num(ind.rsi14, 1)} />
        </Grid>
        <Grid item xs={12} sm={6}>
          <Field label="ADX(14)" value={num(ind.adx14, 1)} />
        </Grid>
        <Grid item xs={12} sm={6}>
          <Field
            label={`EMA Fast${ind.ema_fast ? ` (${ind.ema_fast})` : ''}`}
            value={num(ind.ema_fast_value, 2)}
            hint={hints.ema_fast}
          />
        </Grid>
        <Grid item xs={12} sm={6}>
          <Field
            label={`EMA Slow${ind.ema_slow ? ` (${ind.ema_slow})` : ''}`}
            value={num(ind.ema_slow_value, 2)}
            hint={hints.ema_slow}
          />
        </Grid>
        <Grid item xs={12} sm={6}>
          <Field label="ATR %" value={pct(ind.atr_pct)} />
        </Grid>
        <Grid item xs={12} sm={6}>
          <Field label="RelVol(20)" value={relvol(ind.relvol20)} />
        </Grid>
        <Grid item xs={12}>
          <Field label="vs 52W High" value={prox52w(ind.proximity_52w_high_pct)} />
        </Grid>
      </Grid>
    </BoxedSection>
  );
}

/** Shared section shell: larger header + clean divider (keeps the visual rhythm consistent) */
const BoxedSection: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <div style={{ marginBottom: 16 }}>
    <Typography variant="subtitle1" sx={{ fontWeight: 700, letterSpacing: '.04em', color: 'text.secondary' }}>
      {title}
    </Typography>
    <Divider sx={{ mt: 0.75, mb: 1.25, opacity: 0.6 }} />
    {children}
  </div>
);
