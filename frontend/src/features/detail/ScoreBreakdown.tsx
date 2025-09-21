// detail/ScoreBreakdown.tsx
import * as React from 'react';
import { Box, Divider, Grid, Stack, Tooltip, Typography } from '@mui/material';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';

type Props = {
  score?: number | null;
  trend_rank?: number | null;
  breakout_quality?: number | null;
  relvol?: number | null;
  scales?: Partial<{
    total: 100 | 10 | 1;
    trend: 100 | 10 | 1;
    breakout: 100 | 10 | 1;
    relvol: 100 | 10 | 1;
  }>;
  hints?: Partial<Record<'score' | 'trend' | 'breakout' | 'relvol', string>>;
};

const isNum = (v: unknown): v is number => typeof v === 'number' && isFinite(v);
const clamp01 = (v: number) => Math.max(0, Math.min(100, v));

function detectDen(v?: number | null): 100 | 10 | 1 {
  if (!isNum(v)) return 100;
  if (v <= 1) return 1;
  if (v <= 10) return 10;
  return 100;
}
function toPercent(value?: number | null, den: 100 | 10 | 1 = 100): number | null {
  if (!isNum(value)) return null;
  if (den === 1) return clamp01(value * 100);
  return clamp01((value / den) * 100);
}
const colorFor = (pct?: number | null) => {
  if (!isNum(pct)) return 'text.secondary';
  if (pct >= 80) return 'success.main';
  if (pct >= 60) return 'info.main';
  if (pct >= 40) return 'warning.main';
  return 'error.main';
};

const BigNumber: React.FC<{ value?: number | null; den?: 100 | 10 | 1; colorPct?: number | null }> = ({ value, den = 100, colorPct }) => {
  let shown: string = '—';
  if (isNum(value)) {
    if (den === 1) shown = String(Math.round(value * 100));
    else shown = String(Math.round(value));
  }
  const denomText = den === 1 ? '/100' : `/${den}`;
  return (
    <Stack direction="row" spacing={0.75} alignItems="baseline">
      <Typography variant="h5" sx={{ fontVariantNumeric: 'tabular-nums', fontWeight: 800, color: colorFor(colorPct) as any }}>
        {shown}
      </Typography>
      {isNum(value) ? <Typography variant="caption" color="text.secondary">{denomText}</Typography> : null}
    </Stack>
  );
};

const InlineRow: React.FC<{ label: string; value?: number | null; den?: 100 | 10 | 1; hint?: string }> = ({ label, value, den, hint }) => {
  const d = den ?? detectDen(value);
  const pct = toPercent(value, d);
  const denomText = d === 1 ? '/100' : `/${d}`;
  const main = isNum(value) ? (d === 1 ? Math.round(value * 100) : Math.round(value)) : null;

  return (
    <Stack direction="row" alignItems="baseline" spacing={1} sx={{ justifyContent: 'space-between' }}>
      <Stack direction="row" spacing={0.5} alignItems="center" sx={{ color: 'text.secondary' }}>
        <Typography variant="body2">{label}</Typography>
        {hint ? (
          <Tooltip title={hint}>
            <InfoOutlinedIcon sx={{ fontSize: 14, opacity: 0.7 }} />
          </Tooltip>
        ) : null}
      </Stack>

      {main === null ? (
        <Typography variant="body2" sx={{ fontVariantNumeric: 'tabular-nums' }}>—</Typography>
      ) : (
        <Stack direction="row" spacing={0.5} alignItems="baseline">
          <Typography variant="body2" sx={{ fontVariantNumeric: 'tabular-nums', fontWeight: 700, color: colorFor(pct) as any }}>
            {main}
          </Typography>
          <Typography variant="caption" color="text.secondary">{denomText}</Typography>
        </Stack>
      )}
    </Stack>
  );
};

export default function ScoreBreakdown({
  score,
  trend_rank,
  breakout_quality,
  relvol,
  scales,
  hints = {},
}: Props) {
  const totalDen = (scales?.total ?? 100) as 100 | 10 | 1;
  const totalPct = toPercent(score, totalDen);

  return (
    <Box sx={{ mb: 2 }}>
      <Typography variant="subtitle1" sx={{ fontWeight: 700, letterSpacing: '.04em', color: 'text.secondary' }}>
        Score Breakdown
      </Typography>
      <Divider sx={{ mt: 0.75, mb: 1.25, opacity: 0.6 }} />

      <Grid container spacing={2}>
        {/* Left: Total score */}
        <Grid item xs={12} sm={5}>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
            Total Score
          </Typography>
          <BigNumber value={score} den={totalDen} colorPct={totalPct} />
        </Grid>

        {/* Right: sub-metrics (inline values beside labels) */}
        <Grid item xs={12} sm={7}>
          <Stack spacing={1}>
            <InlineRow
              label="Trend"
              value={trend_rank}
              den={(scales?.trend ?? detectDen(trend_rank)) as 100 | 10 | 1}
              hint={hints.trend}
            />
            <InlineRow
              label="Breakout Quality"
              value={breakout_quality}
              den={(scales?.breakout ?? detectDen(breakout_quality)) as 100 | 10 | 1}
              hint={hints.breakout}
            />
            <InlineRow
              label="Accumulation / RelVol"
              value={relvol}
              den={(scales?.relvol ?? detectDen(relvol)) as 100 | 10 | 1}
              hint={hints.relvol}
            />
          </Stack>
        </Grid>
      </Grid>
    </Box>
  );
}
