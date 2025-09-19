import * as React from 'react';
import { Chip, Stack, Typography } from '@mui/material';
import NotificationsActiveIcon from '@mui/icons-material/NotificationsActive';

export default function AlertsRow({ templates }: { templates?: any[] | null }) {
  const items =
    Array.isArray(templates) && templates.length > 0
      ? templates.map((t) => String(t?.label ?? 'Alert'))
      : ['Price crosses ₹X', 'Enters breakout', 'Close < EMAₙ', 'Breakeven active', 'Stop hit'];

  return (
    <Box sx={{ mb: 2 }}>
      <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
        Alerts
      </Typography>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ flexWrap: 'wrap' }}>
        {items.map((lbl) => (
          <Chip key={lbl} icon={<NotificationsActiveIcon />} label={lbl} variant="outlined" />
        ))}
      </Stack>
    </Box>
  );
}

import { Box } from '@mui/material';
