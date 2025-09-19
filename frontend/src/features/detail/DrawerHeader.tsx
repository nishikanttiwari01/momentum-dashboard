import * as React from 'react';
import { Box, Chip, IconButton, Stack, Typography } from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import { num, pct } from './utils';

type Props = {
  name?: string;
  sector?: string;
  price?: number;
  pctToday?: number;
  runId?: string;
  badges?: string[];
  onClose: () => void;
};

export default function DrawerHeader({
  name,
  sector,
  price,
  pctToday,
  runId,
  badges = [],
  onClose,
}: Props) {
  const pctColor =
    typeof pctToday === 'number'
      ? pctToday >= 0
        ? 'success.main'
        : 'error.main'
      : 'text.secondary';

  return (
    <>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
        <Box>
          <Typography variant="h6" sx={{ fontWeight: 700 }}>
            {name || '—'}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {sector || '—'}
          
          </Typography>
        </Box>

        <Box textAlign="right">
          <Typography variant="h6" sx={{ fontVariantNumeric: 'tabular-nums' }}>
            {num(price)}
          </Typography>
          <Typography
            variant="body2"
            sx={{ color: pctColor, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}
          >
            {pct(pctToday)}
          </Typography>
        </Box>

        <IconButton onClick={onClose} aria-label="close">
          <CloseIcon />
        </IconButton>
      </Stack>

      {badges.length > 0 && (
        <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap', mb: 1 }}>
          {badges.map((b, i) => (
            <Chip key={`badge-${i}`} label={b} size="small" />
          ))}
        </Stack>
      )}
    </>
  );
}
