import * as React from 'react';
import {
  Drawer,
  Box,
  Typography,
  Chip,
  Divider,
  Grid,
  LinearProgress,
  Tooltip,
  IconButton,
  Button,
  Stack,
  TextField,
  Switch,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import WhatshotIcon from '@mui/icons-material/Whatshot';
import SpeedIcon from '@mui/icons-material/Speed';
import NotificationsActiveIcon from '@mui/icons-material/NotificationsActive';
import type { DrawerDetail } from '../lib/api/types';
import { useInstrumentDetail } from '../lib/hooks';

type Props = {
  symbol: string | null;
  open: boolean;
  onClose: () => void;
};

/** Simple formatters */
const pct = (v?: number, digits = 2) =>
  typeof v === 'number' && isFinite(v) ? `${v.toFixed(digits)}%` : '—';
const num = (v?: number, digits = 2) =>
  typeof v === 'number' && isFinite(v) ? v.toFixed(digits) : '—';
const relvol = (v?: number) =>
  typeof v === 'number' && isFinite(v) ? `${v.toFixed(2)}×` : '—';
const prox52w = (p?: number) => {
  if (typeof p !== 'number' || !isFinite(p)) return '—';
  if (p === 0) return 'At 52W high';
  return p > 0 ? `${pct(p)} above` : `${pct(Math.abs(p))} below`;
};

/** Tiny bar with number on the right */
const BarRow: React.FC<{ label: string; value?: number; max?: number }> = ({ label, value, max = 100 }) => {
  const v = typeof value === 'number' && isFinite(value) ? Math.max(0, Math.min(max, value)) : undefined;
  return (
    <Box>
      <Stack direction="row" alignItems="center" spacing={1} mb={0.5}>
        <Typography variant="body2" sx={{ width: 160, color: 'text.secondary' }}>
          {label}
        </Typography>
        <Box sx={{ flex: 1 }}>
          {typeof v === 'number' ? (
            <LinearProgress variant="determinate" value={(v / max) * 100} />
          ) : (
            <Box sx={{ height: 8, bgcolor: 'action.hover', borderRadius: 1 }} />
          )}
        </Box>
        <Typography variant="body2" sx={{ width: 44, textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
          {typeof v === 'number' ? Math.round(v) : '—'}
        </Typography>
      </Stack>
    </Box>
  );
};

/** Meter 0–100 with semantic color */
const Meter: React.FC<{ label: string; value?: number }> = ({ label, value }) => {
  const v = typeof value === 'number' && isFinite(value) ? Math.max(0, Math.min(100, value)) : undefined;
  const color =
    typeof v !== 'number'
      ? 'action.disabledBackground'
      : v < 34
      ? 'success.main'
      : v < 67
      ? 'warning.main'
      : 'error.main';
  return (
    <Box>
      <Typography variant="body2" sx={{ mb: 0.5, color: 'text.secondary' }}>
        {label}
      </Typography>
      <Box sx={{ height: 8, bgcolor: 'action.hover', borderRadius: 999, overflow: 'hidden' }}>
        <Box sx={{ width: `${v ?? 0}%`, height: '100%', bgcolor: color, transition: 'width .3s' }} />
      </Box>
      <Typography variant="caption" sx={{ mt: 0.5, display: 'inline-block', fontVariantNumeric: 'tabular-nums' }}>
        {typeof v === 'number' ? `${v}` : '—'}
      </Typography>
    </Box>
  );
};

export default function RightDrawer({ symbol, open, onClose }: Props) {
  const enabled = Boolean(open && symbol);
  const { data, isLoading, isFetching, error } = useInstrumentDetail(symbol || '', undefined, {
    enabled,
    staleTimeMs: 60_000,
  });

  // Using `any` on read protects us if schema field names differ slightly
  const d = (data as DrawerDetail | undefined) as any;

  // Header chips (badges)
  const badges: string[] = Array.isArray(d?.badges) ? d.badges : [];

  // Entry module local UI (toggle + inputs)
  const [tradeOn, setTradeOn] = React.useState<boolean>(Boolean(d?.entry_block?.locked));
  const [entryPrice, setEntryPrice] = React.useState<string>(d?.entry_block?.entry ? String(d.entry_block.entry) : '');
  const [qty, setQty] = React.useState<string>('');

  React.useEffect(() => {
    setTradeOn(Boolean(d?.entry_block?.locked));
    setEntryPrice(d?.entry_block?.entry ? String(d.entry_block.entry) : '');
  }, [d?.entry_block?.locked, d?.entry_block?.entry]);

  const lockDisabled = !tradeOn || !entryPrice || Number(entryPrice) <= 0;

  return (
    <Drawer anchor="right" open={open} onClose={onClose} PaperProps={{ sx: { width: 480, p: 2 } }}>
      {/* Header */}
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
        <Box>
          <Typography variant="h6" sx={{ fontWeight: 700 }}>
            {d?.name || symbol || '—'}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {d?.sector ? d.sector : '—'}
            {d?.resolved_run_id ? ` · Run ${d.resolved_run_id}` : ''}
          </Typography>
        </Box>
        <Box textAlign="right">
          <Typography variant="h6" sx={{ fontVariantNumeric: 'tabular-nums' }}>
            {num(d?.price)}
          </Typography>
          <Typography
            variant="body2"
            sx={{
              color: typeof d?.change_pct_1d === 'number' ? (d.change_pct_1d >= 0 ? 'success.main' : 'error.main') : 'text.secondary',
              fontWeight: 700,
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            {pct(d?.change_pct_1d ?? d?.change_pct)}
          </Typography>
        </Box>
        <IconButton onClick={onClose} aria-label="close">
          <CloseIcon />
        </IconButton>
      </Stack>

      {/* Badges */}
      {badges.length > 0 && (
        <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap', mb: 1 }}>
          {badges.map((b: string, i: number) => (
            <Chip key={`badge-${i}`} label={b} size="small" />
          ))}
        </Stack>
      )}

      {/* Sparkline placeholder (slot for later chart) */}
      <Box sx={{ height: 80, bgcolor: 'action.hover', borderRadius: 1, mb: 2 }} title="30D sparkline (coming soon)" />

      {/* Indicators grid */}
      <Box sx={{ mb: 2 }}>
        <Grid container spacing={1.5}>
          <Grid item xs={6}>
            <Field label="RSI(14)" value={num(d?.rsi14, 1)} />
          </Grid>
          <Grid item xs={6}>
            <Field label="ADX(14)" value={num(d?.adx14, 1)} />
          </Grid>
          <Grid item xs={6}>
            <Field label="EMA Fast" value={num(d?.ema_fast, 2)} />
          </Grid>
          <Grid item xs={6}>
            <Field label="EMA Slow" value={num(d?.ema_slow, 2)} />
          </Grid>
          <Grid item xs={6}>
            <Field label="ATR %" value={pct(d?.atr_pct)} />
          </Grid>
          <Grid item xs={6}>
            <Field label="RelVol(20)" value={relvol(d?.relvol20)} />
          </Grid>
          <Grid item xs={12}>
            <Field label="vs 52W High" value={prox52w(d?.proximity_52w_high_pct)} />
          </Grid>
        </Grid>
      </Box>

      {/* Score breakdown */}
      <Box sx={{ mb: 2 }}>
        <Typography variant="subtitle2" sx={{ mb: 1 }}>
          Score Breakdown
        </Typography>
        <BarRow label="Total Score" value={d?.score} />
        {/* Optional sub-pillars if present */}
        {'trend_rank' in (d || {}) || 'breakout_quality' in (d || {}) || 'relvol' in (d || {}) ? (
          <>
            {'trend_rank' in (d || {}) && <BarRow label="Trend" value={d?.trend_rank} />}
            {'breakout_quality' in (d || {}) && <BarRow label="Breakout Quality" value={d?.breakout_quality} />}
            {'relvol' in (d || {}) && <BarRow label="Accumulation / RelVol" value={d?.relvol} />}
          </>
        ) : null}
      </Box>

      {/* Meters */}
      <Box sx={{ mb: 2 }}>
        <Typography variant="subtitle2" sx={{ mb: 1 }}>
          Meters
        </Typography>
        <Grid container spacing={1.5}>
          <Grid item xs={6}>
            <Stack direction="row" spacing={1} alignItems="center">
              <SpeedIcon fontSize="small" />
              <Meter label="Risk" value={d?.meters?.risk?.value} />
            </Stack>
          </Grid>
          <Grid item xs={6}>
            <Stack direction="row" spacing={1} alignItems="center">
              <WhatshotIcon fontSize="small" />
              <Meter label="Euphoria" value={d?.meters?.euphoria?.value} />
            </Stack>
          </Grid>
        </Grid>
      </Box>

      {/* Next Action */}
      <Box sx={{ mb: 2 }}>
        <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
          Next Action
        </Typography>
        <Typography variant="body2">
          {d?.next_action?.text ||
            d?.next_action?.reason ||
            d?.next_action?.state ||
            '—'}
        </Typography>
      </Box>

      {/* Entry module */}
      <Box sx={{ mb: 2 }}>
        <Typography variant="subtitle2" sx={{ mb: 1 }}>
          Entry
        </Typography>
        <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
          <Switch
            checked={tradeOn}
            onChange={(e) => setTradeOn(e.target.checked)}
            inputProps={{ 'aria-label': 'Trade toggle' }}
          />
          <Typography variant="body2">Trade</Typography>
        </Stack>

        {tradeOn && (
          <Stack direction="row" spacing={1} sx={{ mb: 1 }}>
            <TextField
              size="small"
              label="Entry price (₹)"
              value={entryPrice}
              onChange={(e) => setEntryPrice(e.target.value)}
              sx={{ width: 180 }}
              inputProps={{ inputMode: 'decimal' }}
            />
            <TextField
              size="small"
              label="Qty"
              value={qty}
              onChange={(e) => setQty(e.target.value)}
              sx={{ width: 120 }}
              inputProps={{ inputMode: 'numeric' }}
            />
            <Button variant="contained" disabled={lockDisabled}>
              Lock entry
            </Button>
          </Stack>
        )}

        <Stack spacing={0.5}>
          <KV label="Stop-loss (now)" value={d?.entry_block?.stop_loss ? `₹${num(d?.entry_block?.stop_loss)}` : '—'} help="sell if touched" />
          <KV label="Exit at close if" value={d?.entry_block?.exit_if ? `Close < ₹${num(d?.entry_block?.exit_if)}` : '—'} help="sell next day if true" />
          <KV label="Breakeven" value={d?.entry_block?.breakeven_at ? `Active at ₹${num(d?.entry_block?.breakeven_at)}` : 'Pending'} help="stop won’t go below entry" />
          <KV label="Euphoria" value={d?.entry_block?.euphoria_on ? 'On' : 'Off'} help="tighter stop & faster EMA" />
        </Stack>
      </Box>

      {/* Alerts row */}
      <Box sx={{ mb: 2 }}>
        <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
          Alerts
        </Typography>
        <Stack direction="row" spacing={1} alignItems="center" sx={{ flexWrap: 'wrap' }}>
          <Chip icon={<NotificationsActiveIcon />} label="Price crosses ₹X" variant="outlined" />
          <Chip icon={<NotificationsActiveIcon />} label="Enters breakout" variant="outlined" />
          <Chip icon={<NotificationsActiveIcon />} label="Close < EMAₙ" variant="outlined" />
          <Chip icon={<NotificationsActiveIcon />} label="Breakeven active" variant="outlined" />
          <Chip icon={<NotificationsActiveIcon />} label="Stop hit" variant="outlined" />
        </Stack>
      </Box>

      {/* Footer info */}
      <Divider sx={{ my: 1.5 }} />
      <Typography variant="caption" color="text.secondary">
        {d?.as_of ? `As of ${new Date(d.as_of).toLocaleString()}` : ''}
        {isFetching ? ' · refreshing…' : ''}
      </Typography>

      {/* Error */}
      {error ? (
        <Typography variant="body2" color="error" sx={{ mt: 1 }}>
          {(error as any)?.message || 'Failed to load details.'}
        </Typography>
      ) : null}
    </Drawer>
  );
}

/** Small label:value inline row */
const KV: React.FC<{ label: string; value: React.ReactNode; help?: string }> = ({ label, value, help }) => (
  <Stack direction="row" spacing={1} alignItems="baseline">
    <Typography variant="body2" sx={{ width: 140, color: 'text.secondary' }}>
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

/** Small label:value simple field */
const Field: React.FC<{ label: string; value: React.ReactNode }> = ({ label, value }) => (
  <Stack direction="row" spacing={1} alignItems="baseline">
    <Typography variant="body2" sx={{ width: 140, color: 'text.secondary' }}>
      {label}:
    </Typography>
    <Typography variant="body2" sx={{ fontVariantNumeric: 'tabular-nums' }}>
      {value}
    </Typography>
  </Stack>
);
