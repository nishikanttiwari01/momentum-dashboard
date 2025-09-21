import * as React from 'react';
import { Chip, Stack } from '@mui/material';
import NotificationsActiveIcon from '@mui/icons-material/NotificationsActive';
import type { AlertTemplate } from '@/lib/api/types';

type Props = { templates?: AlertTemplate[] | null; dense?: boolean };

export default function AlertsRow({ templates, dense = true }: Props) {
  const items =
    Array.isArray(templates) && templates.length > 0
      ? templates.map((t, idx) => ({
          key: t?.code ?? t?.label ?? t?.example ?? `alert-${idx}`,
          label: String(t?.label ?? t?.code ?? t?.example ?? 'Alert'),
        }))
      : [
          { key: 'price-x', label: 'Price crosses ₹X' },
          { key: 'breakout', label: 'Enters breakout' },
          { key: 'ema', label: 'Close < EMAₙ' },
          { key: 'breakeven', label: 'Breakeven active' },
          { key: 'stop', label: 'Stop hit' },
        ];

  return (
    <Stack direction="row" spacing={1} alignItems="center" sx={{ flexWrap: 'wrap' }}>
      {items.map((it) => (
        <Chip
          key={it.key}
          icon={<NotificationsActiveIcon />}
          size={dense ? 'small' : 'medium'}
          label={it.label}
          variant="outlined"
        />
      ))}
    </Stack>
  );
}
