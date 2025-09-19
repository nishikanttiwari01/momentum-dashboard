import * as React from 'react';
import { Chip, Grid, Stack, Tooltip, Typography } from '@mui/material';
import SpeedIcon from '@mui/icons-material/Speed';
import WhatshotIcon from '@mui/icons-material/Whatshot';
import { levelColor } from './utils';

type MeterNode = { level?: string; basis?: Record<string, number> | null };

export default function Meters({ risk, euphoria }: { risk?: MeterNode; euphoria?: MeterNode }) {
  const basisToText = (b?: Record<string, number> | null) =>
    b && Object.keys(b).length
      ? Object.entries(b)
          .map(([k, v]) => `${k}: ${typeof v === 'number' ? v.toFixed(2) : String(v)}`)
          .join(' · ')
      : undefined;

  return (
    <Box sx={{ mb: 2 }}>
      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        Meters
      </Typography>
      <Grid container spacing={1.5}>
        <Grid item xs={6}>
          <Stack direction="row" spacing={1} alignItems="center">
            <SpeedIcon fontSize="small" />
            <Tooltip title={basisToText(risk?.basis) || ''} disableHoverListener={!risk?.basis}>
              <Chip size="small" color={levelColor(risk?.level) as any} label={`Risk: ${risk?.level ?? '—'}`} />
            </Tooltip>
          </Stack>
        </Grid>
        <Grid item xs={6}>
          <Stack direction="row" spacing={1} alignItems="center">
            <WhatshotIcon fontSize="small" />
            <Tooltip title={basisToText(euphoria?.basis) || ''} disableHoverListener={!euphoria?.basis}>
              <Chip
                size="small"
                color={levelColor(euphoria?.level) as any}
                label={`Euphoria: ${euphoria?.level ?? '—'}`}
              />
            </Tooltip>
          </Stack>
        </Grid>
      </Grid>
    </Box>
  );
}

import { Box } from '@mui/material';
