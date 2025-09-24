// detail/ActionBlock.tsx
import * as React from 'react';
import { Box, Typography, Divider, Grid } from '@mui/material';
import { rup } from './utils';

type Props = {
  stop_now?: number;
  stop_method?: string;             // new (e.g., 'ATR10', 'SwingLow')
  exit_close_threshold?: number;

  // legacy fields
  breakeven_active?: boolean;
  euphoria_on?: boolean;

  // new fields
  breakeven_state?: string;         // 'Active' | 'Pending' | etc.
  euphoria_state?: string;          // 'On' | 'Off' | etc.
};

const KVRow: React.FC<{ label: string; value?: React.ReactNode; help?: string }> = ({ label, value, help }) => {
  if (value == null || value === '' || value === false) {
    // still show help if present (layout stays consistent)
    return (
      <Grid container spacing={1} alignItems="baseline" sx={{ mt: 0.25 }}>
        <Grid item xs={5} sm={4}>
          <Typography variant="body2" sx={{ color: 'text.secondary' }}>{label}:</Typography>
        </Grid>
        <Grid item xs={7} sm={4}>
          <Typography variant="body2" sx={{ fontVariantNumeric: 'tabular-nums' }}>—</Typography>
        </Grid>
        <Grid item xs={12} sm={4}>
          {help ? <Typography variant="caption" color="text.secondary">{help}</Typography> : null}
        </Grid>
      </Grid>
    );
  }

  return (
    <Grid container spacing={1} alignItems="baseline" sx={{ mt: 0.25 }}>
      <Grid item xs={5} sm={4}>
        <Typography variant="body2" sx={{ color: 'text.secondary' }}>{label}:</Typography>
      </Grid>
      <Grid item xs={7} sm={4}>
        <Typography variant="body2" sx={{ fontVariantNumeric: 'tabular-nums' }}>{value}</Typography>
      </Grid>
      <Grid item xs={12} sm={4}>
        {help ? <Typography variant="caption" color="text.secondary">{help}</Typography> : null}
      </Grid>
    </Grid>
  );
};

function prettyState(primary?: string, legacyOn?: boolean, legacyActive?: boolean) {
  if (typeof primary === 'string' && primary.trim()) return primary;
  if (typeof legacyOn === 'boolean') return legacyOn ? 'On' : 'Off';
  if (typeof legacyActive === 'boolean') return legacyActive ? 'Active' : 'Pending';
  return '—';
}

export default function StopLossAction({
  stop_now,
  stop_method,
  exit_close_threshold,
  breakeven_active,
  euphoria_on,
  breakeven_state,
  euphoria_state,
}: Props) {
  // Debug logging for observability (safe, minimal)
  React.useEffect(() => {
    try {
      // only log when something meaningful changes
      // eslint-disable-next-line no-console
      console.debug('[StopLossAction]', {
        stop_now, stop_method, exit_close_threshold,
        breakeven_state, euphoria_state,
        breakeven_active, euphoria_on,
      });
    } catch { /* no-op */ }
  }, [stop_now, stop_method, exit_close_threshold, breakeven_state, euphoria_state, breakeven_active, euphoria_on]);

  // Derived display strings
  const stopHelp = `Sell if touched${stop_method ? ` (${stop_method})` : ''}`;
  const exitHelp = 'Sell next day if true';
  const breakevenHelp = 'Stop won’t go below entry';
  const euphoriaHelp = 'Tighter stop & faster EMA';

  const breakevenVal = prettyState(breakeven_state, undefined, breakeven_active);
  const euphoriaVal = prettyState(euphoria_state, euphoria_on, undefined);

  return (
    <Box sx={{ mb: 2 }}>
      {/* Section header + line */}
      <Typography variant="subtitle1" sx={{ fontWeight: 700, letterSpacing: '.04em', color: 'text.secondary' }}>
        Stop-loss Action
      </Typography>
      <Divider sx={{ mt: 0.75, mb: 1.25, opacity: 0.6 }} />

      {/* Rows: label | value | suggestion */}
      <KVRow
        label="Stop-loss (now)"
        value={typeof stop_now === 'number' && stop_now > 0 ? rup(stop_now) : undefined}
        help={stopHelp}
      />

      <KVRow
        label="Exit at close if"
        value={typeof exit_close_threshold === 'number' && exit_close_threshold > 0 ? <>Close &lt; {rup(exit_close_threshold)}</> : undefined}
        help={exitHelp}
      />

      <KVRow
        label="Breakeven"
        value={breakevenVal}
        help={breakevenHelp}
      />

      <KVRow
        label="Euphoria"
        value={euphoriaVal}
        help={euphoriaHelp}
      />
    </Box>
  );
}
