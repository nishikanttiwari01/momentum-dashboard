import * as React from 'react';
import { Chip, Stack, Typography } from '@mui/material';
import { num, rup } from './utils';

type Refs = {
  ema_n?: number;
  ema_value?: number;
  entry_suggested?: number;
  entry_low?: number | null;
  entry_high?: number | null;
  entry_type?: string | null;
};

type Props = {
  text?: string;
  refs?: Refs;
  method_pill?: string;
};

export default function NextAction({ text, refs = {}, method_pill }: Props) {
  return (
    <Box sx={{ mb: 2 }}>
      <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
        Next Action
      </Typography>
      <Typography variant="body2" sx={{ fontWeight: 600 }}>
        {text || '—'}
      </Typography>

      <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 0.5, color: 'text.secondary' }}>
        {typeof refs.ema_n === 'number' && typeof refs.ema_value === 'number' ? (
          <Chip size="small" variant="outlined" label={`EMA${refs.ema_n}=${num(refs.ema_value, 2)}`} />
        ) : null}
        {typeof refs.entry_suggested === 'number' ? (
          <Chip size="small" variant="outlined" label={`Suggested Entry ${rup(refs.entry_suggested)}`} />
        ) : null}
        {typeof refs.entry_low === 'number' && typeof refs.entry_high === 'number' ? (
          <Chip size="small" variant="outlined" label={`Entry Band ${rup(refs.entry_low)}–${rup(refs.entry_high)}`} />
        ) : null}
        {refs.entry_type ? <Chip size="small" variant="outlined" label={refs.entry_type} /> : null}
        {method_pill ? <Chip size="small" color="default" label={method_pill} /> : null}
      </Stack>
    </Box>
  );
}

import { Box } from '@mui/material';
