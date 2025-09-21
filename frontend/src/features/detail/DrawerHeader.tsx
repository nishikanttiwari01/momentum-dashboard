// detail/DrawerHeader.tsx
import * as React from 'react';
import { Box, Chip, IconButton, Stack, Typography } from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import { num, pct } from './utils';
import type { Badge as ApiBadge } from '@/lib/api/types';

type Props = {
  name?: string;
  sector?: string;
  price?: number;
  pctToday?: number;
  runId?: string;
  badges?: ApiBadge[] | Array<string | number>;
  onClose: () => void;
};

const muiColors = new Set(['default','primary','secondary','success','info','warning','error']);

const normBadge = (b: unknown) => {
  if (b == null) return { label: '—', color: 'default' as const };

  // primitives
  if (typeof b === 'string' || typeof b === 'number') {
    return { label: String(b), color: 'default' as const };
  }

  // typed/loose objects
  const x = b as any;

  // new contract support: { category, label }
  if ('category' in x || 'label' in x) {
    const label = String(x.label ?? x.text ?? x.code ?? x.key ?? 'Badge');
    const cat = String(x.category ?? '').toUpperCase();
    const color =
      muiColors.has(x.color) ? (x.color as any) :
      cat === 'BREAKOUT' ? 'warning' :
      cat === 'MOMENTUM' ? 'success' :
      cat === 'IGNORE'   ? 'error'   :
      cat === 'WATCH'    ? 'info'    : 'default';
    return { label, color };
  }

  // legacy object
  const label = x.label ?? x.text ?? x.code ?? x.key ?? 'Badge';
  const color = x.color && muiColors.has(x.color) ? (x.color as any) : 'default';
  return { label, color };
};

export default function DrawerHeader({
  name, sector, price, pctToday, runId, badges: rawBadges, onClose,
}: Props) {
  const badges = Array.isArray(rawBadges) ? rawBadges : [];
  const pctColor =
    typeof pctToday === 'number'
      ? (pctToday >= 0 ? 'success.main' : 'error.main')
      : 'text.secondary';

  return (
    <>
      {/* Title row */}
      <Stack direction="row" alignItems="flex-start" justifyContent="space-between">
        <Box sx={{ minWidth: 0, pr: 1 }}>
          <Typography
            variant="h6"
            sx={{ fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
            title={name || '—'}
          >
            {name || '—'}
          </Typography>

          {/* subline: sector · run */}
        
        </Box>

        {/* price + inline % (colored), no chip */}
        <Stack direction="row" spacing={1} alignItems="baseline" sx={{ flexShrink: 0 }}>
                       <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
            title={[sector, runId ? `Run ${runId}` : ''].filter(Boolean).join(' · ')}
          >
            {sector || 'Today'}
          </Typography>
          <Typography variant="h6" sx={{ fontVariantNumeric: 'tabular-nums' }}>
            {num(price)}
          </Typography>
          <Typography
            variant="body2"
            sx={{ color: pctColor, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}
            title="Change today"
          >
            {pct(pctToday)}
          </Typography>
          <IconButton onClick={onClose} aria-label="close" size="small" sx={{ ml: 0.5 }}>
            <CloseIcon fontSize="small" />
          </IconButton>
 
        </Stack>
      
      </Stack>

      {/* badges row */}
      {badges.length > 0 && (
        <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap', mt: 1 }}>
          {badges.slice(0, 8).map((b, i) => {
            const nb = normBadge(b);
            return (
              <Chip
                key={`badge-${i}`}
                size="small"
                variant={nb.color === 'default' ? 'outlined' : 'filled'}
                color={nb.color as any}
                label={nb.label}
              />
            );
          })}
        </Stack>
      )}
    </>
  );
}
