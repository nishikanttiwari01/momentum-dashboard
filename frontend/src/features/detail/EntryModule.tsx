import * as React from 'react';
import { Button, Stack, Switch, TextField, Tooltip, Typography } from '@mui/material';
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

  const lockDisabled = !trade_on || !entryPrice || Number(entryPrice) <= 0 || (q && Number(q) <= 0);

  return (
    <Box sx={{ mb: 2 }}>
      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        Entry
      </Typography>

      <KV
        label="Entry price"
        value={rup(typeof effectiveEntry === 'number' ? effectiveEntry : undefined)}
        help={locked ? 'Locked' : 'Suggested (can lock when Trade ON)'}
      />

      <Stack direction="row" alignItems="center" spacing={1} sx={{ mt: 1, mb: 1 }}>
        <Switch checked={!!trade_on} onChange={(e) => onTradeChange?.(e.target.checked)} />
        <Typography variant="body2">Trade</Typography>
        {locked && (
          <Tooltip title="Entry is locked; adjust via dedicated flow">
            <InfoOutlinedIcon fontSize="small" />
          </Tooltip>
        )}
      </Stack>

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
            sx={{ width: 180 }}
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
            sx={{ width: 120 }}
            inputProps={{ inputMode: 'numeric' }}
            disabled={locked}
          />
          <Button variant="contained" disabled={lockDisabled || !!locked}>
            Lock entry
          </Button>
        </Stack>
      )}
    </Box>
  );
}

const KV: React.FC<{ label: string; value: React.ReactNode; help?: string }> = ({ label, value, help }) => (
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

import { Box } from '@mui/material';
