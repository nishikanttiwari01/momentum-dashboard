// detail/NextAction.tsx
import * as React from 'react';
import { Box, Stack, Typography, Divider, Tooltip } from '@mui/material';
import InfoTooltip from '@/components/InfoTooltip';
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
  React.useEffect(() => {
    try {
      // eslint-disable-next-line no-console
      console.debug('[NextAction]', {
        text,
        refs: {
          ema_n: refs?.ema_n, ema_value: refs?.ema_value,
          entry_suggested: refs?.entry_suggested,
          entry_low: refs?.entry_low, entry_high: refs?.entry_high,
          entry_type: refs?.entry_type
        },
        reasons
      });
    } catch { /* no-op */ }
  }, [text, refs?.ema_n, refs?.ema_value, refs?.entry_suggested, refs?.entry_low, refs?.entry_high, refs?.entry_type, reasons]);

  const hasBand = typeof refs.entry_low === 'number' && isFinite(refs.entry_low as number) && typeof refs.entry_high === 'number' && isFinite(refs.entry_high as number);
  const hasEma = typeof refs.ema_n === 'number' && isFinite(refs.ema_n) && typeof refs.ema_value === 'number' && isFinite(refs.ema_value);

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
                EMA{refs.ema_n} @ {rup(refs.ema_value)}
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
                <InfoTooltip body={method_tooltip} iconSize={14} placement="right" />
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
