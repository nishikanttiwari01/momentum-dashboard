// detail/EntryModule.tsx
import * as React from 'react';
import { Box, Button, Divider, Stack, Switch, TextField, Tooltip, Typography } from '@mui/material';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import { rup } from './utils';

type Props = {
  effectiveEntry?: number;
  locked?: boolean;
  trade_on?: boolean;
  qty?: number;
  onTradeChange?: (on: boolean) => void;
  onEntryChange?: (v: string) => void;
  onQtyChange?: (v: string) => void;
};

export default function EntryModule({
  effectiveEntry,
  locked,
  trade_on,
  qty,
  onTradeChange,
  onEntryChange,
  onQtyChange,
}: Props) {
  const [entryPrice, setEntryPrice] = React.useState(
    typeof effectiveEntry === 'number' ? String(effectiveEntry) : ''
  );
  const [q, setQ] = React.useState(qty ? String(qty) : '');

  React.useEffect(() => {
    setEntryPrice(typeof effectiveEntry === 'number' ? String(effectiveEntry) : '');
  }, [effectiveEntry]);

  React.useEffect(() => {
    setQ(qty ? String(qty) : '');
  }, [qty]);

  const lockDisabled =
    !trade_on || !entryPrice || Number(entryPrice) <= 0 || (q && Number(q) <= 0);

  return (
    <Box sx={{ mb: 2 }}>
      {/* Section header + line (consistent with other sections) */}
      <Typography variant="subtitle1" sx={{ fontWeight: 700, letterSpacing: '.04em', color: 'text.secondary' }}>
        Entry
      </Typography>
      <Divider sx={{ mt: 0.75, mb: 1.25, opacity: 0.6 }} />

      <KV
        label="Entry price"
        value={rup(typeof effectiveEntry === 'number' ? effectiveEntry : undefined)}
        help={locked ? 'Locked' : 'Suggested (lock when Trade ON)'}
      />

      {/* Trade toggle */}
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mt: 1, mb: 1 }}>
        <Switch checked={!!trade_on} onChange={(e) => onTradeChange?.(e.target.checked)} />
        <Typography variant="body2">Trade</Typography>
        {locked && (
          <Tooltip title="Entry is locked; adjust via dedicated flow">
            <InfoOutlinedIcon fontSize="small" />
          </Tooltip>
        )}
      </Stack>

      {/* Inline inputs (view-only wiring preserved) */}
      {trade_on && (
        <Stack direction="row" spacing={1} sx={{ mb: 1, flexWrap: 'wrap' }}>
          <TextField
            size="small"
            label="Entry price (₹)"
            value={entryPrice}
            onChange={(e) => {
              setEntryPrice(e.target.value);
              onEntryChange?.(e.target.value);
            }}
            sx={{ width: 200 }}
            inputProps={{ inputMode: 'decimal' }}
            disabled={locked}
          />
          <TextField
            size="small"
            label="Qty"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              onQtyChange?.(e.target.value);
            }}
            sx={{ width: 140 }}
            inputProps={{ inputMode: 'numeric' }}
            disabled={locked}
          />
        </Stack>
      )}
    </Box>
  );
}

const KV: React.FC<{ label: string; value: React.ReactNode; help?: string }> = ({ label, value, help }) => (
  <Stack direction="row" spacing={1} alignItems="baseline">
    <Typography variant="body2" sx={{ width: 160, color: 'text.secondary', flexShrink: 0 }}>
      {label}:
    </Typography>
    <Typography variant="body2" sx={{ fontVariantNumeric: 'tabular-nums' }}>
      {value ?? '—'}
    </Typography>
    {help ? (
      <Typography variant="caption" color="text.secondary">
        — {help}
      </Typography>
    ) : null}
  </Stack>
);
