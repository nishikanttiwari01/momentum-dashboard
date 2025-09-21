// detail/NextAction.tsx
import * as React from 'react';
import { Box, Stack, Typography, Divider, Tooltip } from '@mui/material';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import { num, rup } from './utils';

type Refs = {
  ema_n?: number;
  ema_value?: number;
  entry_suggested?: number;
  entry_low?: number | null;
  entry_high?: number | null;
  entry_type?: string | null;
  [k: string]: unknown;
};

type Props = {
  text?: string;
  refs?: Refs;
  method_pill?: string;
  method_tooltip?: string;
  reasons?: string[];
};

const Row: React.FC<{ label: string; value?: React.ReactNode }> = ({ label, value }) => {
  if (value == null || value === '' || value === false) return null;
  return (
    <Stack direction="row" spacing={1} alignItems="baseline" sx={{ minWidth: 0 }}>
      <Typography variant="body2" sx={{ width: 140, color: 'text.secondary', flexShrink: 0 }}>
        {label}:
      </Typography>
      <Typography variant="body2" sx={{ fontVariantNumeric: 'tabular-nums' }}>
        {value}
      </Typography>
    </Stack>
  );
};

export default function NextAction({ text, refs = {}, method_pill, method_tooltip, reasons }: Props) {
  const hasBand = typeof refs.entry_low === 'number' && typeof refs.entry_high === 'number';
  const hasEma = typeof refs.ema_n === 'number' && typeof refs.ema_value === 'number';

  return (
    <Box sx={{ mb: 2 }}>
      {/* Section header (bigger) */}
      <Typography variant="subtitle1" sx={{ fontWeight: 700, letterSpacing: '.04em', color: 'text.secondary' }}>
        Next Action
      </Typography>
      {/* Stronger, clean divider under header */}
      <Divider sx={{ mt: 0.75, mb: 1.25, opacity: 0.6 }} />

      {/* Primary instruction */}
      <Typography variant="body2" sx={{ fontWeight: 700, mb: 1 }}>
        {text || '—'}
      </Typography>

      {/* Ordered details */}
      <Stack spacing={0.5}>
        {hasEma && (
          <Row
            label="Anchor"
            value={
              <span>
                EMA{refs.ema_n} @ {num(refs.ema_value, 2)}
              </span>
            }
          />
        )}

        <Row
          label="Suggested entry"
          value={typeof refs.entry_suggested === 'number' ? rup(refs.entry_suggested) : undefined}
        />

        {hasBand && (
          <Row
            label="Entry band"
            value={
              <span>
                {rup(refs.entry_low as number)}–{rup(refs.entry_high as number)}
              </span>
            }
          />
        )}

        <Row label="Type" value={refs.entry_type ? String(refs.entry_type) : undefined} />

        {method_pill && (
          <Stack direction="row" spacing={1} alignItems="center">
            <Typography variant="body2" sx={{ width: 140, color: 'text.secondary', flexShrink: 0 }}>
              Method:
            </Typography>
            <Tooltip title={method_tooltip || ''} disableHoverListener={!method_tooltip}>
              <Box
                sx={{
                  px: 1,
                  py: 0.25,
                  borderRadius: 1,
                  bgcolor: 'info.main',
                  color: 'info.contrastText',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 0.5,
                  fontSize: 12,
                  fontWeight: 600,
                }}
              >
                <span>{method_pill}</span>
                <InfoOutlinedIcon sx={{ fontSize: 14, opacity: method_tooltip ? 0.85 : 0.35 }} />
              </Box>
            </Tooltip>
          </Stack>
        )}
      </Stack>

      {Array.isArray(reasons) && reasons.length > 0 && (
        <Box sx={{ mt: 1 }}>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.25 }}>
            Why
          </Typography>
          <Stack component="ul" spacing={0.25} sx={{ pl: 2, m: 0 }}>
            {reasons.slice(0, 6).map((r, i) => (
              <Typography key={i} component="li" variant="caption" color="text.secondary">
                {r}
              </Typography>
            ))}
          </Stack>
        </Box>
      )}
    </Box>
  );
}
