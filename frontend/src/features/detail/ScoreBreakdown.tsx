import * as React from 'react';
import { Box, LinearProgress, Stack, Typography } from '@mui/material';

const BarRow: React.FC<{ label: string; value?: number; max?: number }> = ({
  label,
  value,
  max = 100,
}) => {
  const v =
    typeof value === 'number' && isFinite(value)
      ? Math.max(0, Math.min(max, value))
      : undefined;
  return (
    <Box>
      <Stack direction="row" alignItems="center" spacing={1} mb={0.5}>
        <Typography variant="body2" sx={{ width: 160, color: 'text.secondary' }}>
          {label}
        </Typography>
        <Box sx={{ flex: 1 }}>
          {typeof v === 'number' ? (
            <LinearProgress variant="determinate" value={(v / max) * 100} />
          ) : (
            <Box sx={{ height: 8, bgcolor: 'action.hover', borderRadius: 1 }} />
          )}
        </Box>
        <Typography
          variant="body2"
          sx={{ width: 44, textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}
        >
          {typeof v === 'number' ? Math.round(v) : '—'}
        </Typography>
      </Stack>
    </Box>
  );
};

type Props = {
  score?: number;
  trend_rank?: number;
  breakout_quality?: number;
  relvol?: number;
};

export default function ScoreBreakdown(props: Props) {
  return (
    <Box sx={{ mb: 2 }}>
      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        Score Breakdown
      </Typography>
      <BarRow label="Total Score" value={props.score} />
      {'trend_rank' in props && <BarRow label="Trend" value={props.trend_rank} />}
      {'breakout_quality' in props && (
        <BarRow label="Breakout Quality" value={props.breakout_quality} />
      )}
      {'relvol' in props && <BarRow label="Accumulation / RelVol" value={props.relvol} />}
    </Box>
  );
}
