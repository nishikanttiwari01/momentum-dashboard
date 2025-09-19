import * as React from 'react';
import { Grid, Stack, Typography } from '@mui/material';
import { num, pct, relvol, prox52w } from './utils';

const Field: React.FC<{ label: string; value: React.ReactNode }> = ({ label, value }) => (
  <Stack direction="row" spacing={1} alignItems="baseline">
    <Typography variant="body2" sx={{ width: 160, color: 'text.secondary' }}>
      {label}:
    </Typography>
    <Typography variant="body2" sx={{ fontVariantNumeric: 'tabular-nums' }}>
      {value}
    </Typography>
  </Stack>
);

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

export default function IndicatorsGrid({ ind = {} as Indicators }) {
  return (
    <Grid container spacing={1.5} sx={{ mb: 2 }}>
      <Grid item xs={6}>
        <Field label="RSI(14)" value={num(ind.rsi14, 1)} />
      </Grid>
      <Grid item xs={6}>
        <Field label="ADX(14)" value={num(ind.adx14, 1)} />
      </Grid>
      <Grid item xs={6}>
        <Field
          label={`EMA Fast${ind.ema_fast ? ` (${ind.ema_fast})` : ''}`}
          value={num(ind.ema_fast_value, 2)}
        />
      </Grid>
      <Grid item xs={6}>
        <Field
          label={`EMA Slow${ind.ema_slow ? ` (${ind.ema_slow})` : ''}`}
          value={num(ind.ema_slow_value, 2)}
        />
      </Grid>
      <Grid item xs={6}>
        <Field label="ATR %" value={pct(ind.atr_pct)} />
      </Grid>
      <Grid item xs={6}>
        <Field label="RelVol(20)" value={relvol(ind.relvol20)} />
      </Grid>
      <Grid item xs={12}>
        <Field label="vs 52W High" value={prox52w(ind.proximity_52w_high_pct)} />
      </Grid>
    </Grid>
  );
}
