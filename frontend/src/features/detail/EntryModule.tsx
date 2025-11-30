// detail/EntryModule.tsx
import * as React from 'react';
import { Box, Divider, Stack, Switch, TextField, Typography } from '@mui/material';
import InfoTooltip from '@/components/InfoTooltip';
import { rup } from './utils';

type Props = {
  /** Locked or suggested entry shown above the inputs */
  effectiveEntry?: number;
  /** Optional: pass current market/suggested price for better seeding when unlocked */
  suggestedEntry?: number; // 👈 NEW (optional, backwards-compatible)

  locked?: boolean;
  trade_on?: boolean;
  qty?: number;
  qtyError?: string | null;

  onTradeChange?: (on: boolean) => void;
  onEntryChange?: (v: string) => void;
  onQtyChange?: (v: string) => void;
};

export default function EntryModule({
  effectiveEntry,
  suggestedEntry,      // 👈 NEW
  locked,
  trade_on,
  qty,
  qtyError,
  onTradeChange,
  onEntryChange,
  onQtyChange,
}: Props) {
  // helpers
  const fmt2 = React.useCallback((n?: number) => {
    if (typeof n !== 'number' || Number.isNaN(n)) return '';
    return Number(n).toFixed(2);
  }, []);

  // track previous states to detect transitions
  const prevLockedRef = React.useRef<boolean>(!!locked);
  const prevTradeRef = React.useRef<boolean>(!!trade_on);

  // we cache the last usable suggestion so toggling Trade ON after unlock has a value
  const [lastSuggested, setLastSuggested] = React.useState<string>(
    fmt2(typeof suggestedEntry === 'number' ? suggestedEntry : effectiveEntry)
  );

  // local controlled inputs
  const [entryPrice, setEntryPrice] = React.useState<string>(
    locked ? fmt2(effectiveEntry) : '' // start blank when unlocked
  );
  const [q, setQ] = React.useState<string>(locked && typeof qty === 'number' ? String(qty) : '');

  // Keep a good “seed” around:
  // 1) Prefer explicit suggestedEntry from parent,
  // 2) Else fall back to effectiveEntry when it is a number.
  React.useEffect(() => {
    if (typeof suggestedEntry === 'number') {
      setLastSuggested(fmt2(suggestedEntry));
    } else if (typeof effectiveEntry === 'number') {
      setLastSuggested(fmt2(effectiveEntry));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [suggestedEntry, effectiveEntry, fmt2]);

  // While LOCKED, mirror props into the inputs so the UI reflects DB
  React.useEffect(() => {
    if (locked) {
      setEntryPrice(fmt2(effectiveEntry));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [locked, effectiveEntry, fmt2]);

  React.useEffect(() => {
    if (locked) {
      setQ(typeof qty === 'number' ? String(qty) : '');
    }
  }, [locked, qty]);

  // On UNLOCK (locked: true -> false), clear local inputs and notify parent;
  // remain in control to avoid stale repopulation until a new seed is chosen.
  React.useEffect(() => {
    const wasLocked = prevLockedRef.current;
    if (wasLocked && !locked) {
      setEntryPrice('');
      setQ('');
      onEntryChange?.('');
      onQtyChange?.('');
    }
    prevLockedRef.current = !!locked;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [locked]);

  // When Trade toggles OFF->ON and we are UNLOCKED, seed entry with:
  // suggestedEntry (if provided) OR last seen effectiveEntry; both 2dp.
  React.useEffect(() => {
    const wasOn = prevTradeRef.current;
    const nowOn = !!trade_on;
    if (!wasOn && nowOn && !locked) {
      if (!entryPrice) {
        const seed = lastSuggested || '';
        setEntryPrice(seed);
        if (seed) onEntryChange?.(seed);
      }
    }
    prevTradeRef.current = nowOn;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trade_on, locked, lastSuggested, entryPrice]);

  const lockDisabled =
    !trade_on || !entryPrice || Number(entryPrice) <= 0 || (q && Number(q) <= 0);

  return (
    <Box sx={{ mb: 2 }}>
      {/* Section header */}
      <Typography
        variant="subtitle1"
        sx={{ fontWeight: 700, letterSpacing: '.04em', color: 'text.secondary' }}
      >
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
          <InfoTooltip body="Entry is locked; adjust via dedicated flow" iconSize={16} placement="right" />
        )}
      </Stack>

      {/* Inputs (enabled only when trade_on; disabled when locked) */}
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
            onBlur={() => {
              if (entryPrice && !Number.isNaN(+entryPrice)) {
                const rounded = Number(parseFloat(entryPrice).toFixed(2)).toString();
                setEntryPrice(rounded);
                onEntryChange?.(rounded);
              }
            }}
            sx={{ width: 200 }}
            inputProps={{ inputMode: 'decimal' }}
            disabled={!!locked}
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
            disabled={!!locked}
            error={Boolean(qtyError)}
            helperText={qtyError || ' '}
          />
        </Stack>
      )}
    </Box>
  );
}

const KV: React.FC<{ label: string; value: React.ReactNode; help?: string }> = ({
  label,
  value,
  help,
}) => (
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
