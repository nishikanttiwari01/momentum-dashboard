import * as React from 'react';
import { Stack, Typography } from '@mui/material';
import { rup } from './utils';

const KV: React.FC<{ label: string; value: React.ReactNode; help?: string }> = ({
  label,
  value,
  help,
}) => (
  <Stack direction="row" spacing={1} alignItems="baseline">
    <Typography variant="body2" sx={{ width: 160, color: 'text.secondary' }}>
      {label}:
    </Typography>
    <Typography variant="body2" sx={{ fontVariantNumeric: 'tabular-nums' }}>
      {value}
    </Typography>
    {help ? (
      <Typography variant="caption" color="text.secondary">
        — {help}
      </Typography>
    ) : null}
  </Stack>
);

type Props = {
  stop_now?: number;
  exit_close_threshold?: number;
  breakeven_active?: boolean;
  euphoria_on?: boolean;
};

export default function ActionBlock({
  stop_now,
  exit_close_threshold,
  breakeven_active,
  euphoria_on,
}: Props) {
  return (
    <Box sx={{ mb: 2 }}>
      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        Action
      </Typography>
      <Stack spacing={0.5}>
        <KV label="Stop-loss (now)" value={typeof stop_now === 'number' ? rup(stop_now) : '—'} help="sell if touched" />
        <KV
          label="Exit at close if"
          value={typeof exit_close_threshold === 'number' ? `Close < ${rup(exit_close_threshold)}` : '—'}
          help="sell next day if true"
        />
        <KV
          label="Breakeven"
          value={breakeven_active ? 'Active' : 'Pending'}
          help="stop won’t go below entry"
        />
        <KV label="Euphoria" value={euphoria_on ? 'On' : 'Off'} help="tighter stop & faster EMA" />
      </Stack>
    </Box>
  );
}

import { Box } from '@mui/material';
