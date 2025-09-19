// src/features/detail/RightDrawer.tsx
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
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import type { DrawerDetail } from '../lib/api/types';
import { useInstrumentDetail } from '../lib/hooks';

type Props = {
  symbol: string | null;
  open: boolean;
  onClose: () => void;
};

/* ---------- formatters ---------- */
const pct = (v?: number, digits = 2) =>
  typeof v === 'number' && isFinite(v) ? `${v.toFixed(digits)}%` : '—';
const rup = (v?: number, digits = 2) =>
  typeof v === 'number' && isFinite(v) ? `₹${v.toFixed(digits)}` : '—';
const num = (v?: number, digits = 2) =>
  typeof v === 'number' && isFinite(v) ? v.toFixed(digits) : '—';
const relvol = (v?: number) =>
  typeof v === 'number' && isFinite(v) ? `${v.toFixed(2)}×` : '—';
const prox52w = (p?: number) => {
  if (typeof p !== 'number' || !isFinite(p)) return '—';
  if (p === 0) return 'At 52W high';
  return p > 0 ? `${pct(p)} above` : `${pct(Math.abs(p))} below`;
};
const levelColor = (level?: string) => {
  switch ((level || '').toLowerCase()) {
    case 'low':
      return 'success';
    case 'medium':
      return 'warning';
    case 'high':
      return 'error';
    default:
      return 'default';
  }
};

/* ---------- tiny bar row ---------- */
const BarRow: React.FC<{ label: string; value?: number; max?: number }> = ({
  label,
  value,
  max = 100,
}) => {
  const v =
    typeof value === 'number' && isFinite(value)
      ? Math.max(0, Math.min(max, value))
      : undefined;
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
        <Typography
          variant="body2"
          sx={{ width: 44, textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}
        >
          {typeof v === 'number' ? Math.round(v) : '—'}
        </Typography>
      </Stack>
    </Box>
  );
};

/* ---------- level chip (Risk/Euphoria) ---------- */
const LevelChip: React.FC<{ label: string; level?: string; basis?: Record<string, number> }> = ({
  label,
  level,
  basis,
}) => {
  const color = levelColor(level);
  const kbasis =
    basis && Object.keys(basis).length
      ? Object.entries(basis)
          .map(([k, v]) => `${k}: ${typeof v === 'number' ? v.toFixed(2) : String(v)}`)
          .join(' · ')
      : undefined;
  return (
    <Stack direction="row" spacing={1} alignItems="center">
      {label === 'Risk' ? <SpeedIcon fontSize="small" /> : <WhatshotIcon fontSize="small" />}
      <Tooltip title={kbasis || ''} disableHoverListener={!kbasis}>
        <Chip size="small" color={color as any} label={`${label}: ${level ?? '—'}`} />
      </Tooltip>
    </Stack>
  );
};

/* ---------- simple field rows ---------- */
const KV: React.FC<{ label: string; value: React.ReactNode; help?: string }> = ({
  label,
  value,
  help,
}) => (
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

const Field: React.FC<{ label: string; value: React.ReactNode }> = ({ label, value }) => (
  <Stack direction="row" spacing={1} alignItems="baseline">
    <Typography variant="body2" sx={{ width: 160, color: 'text.secondary' }}>
      {label}:
    </Typography>
    <Typography variant="body2" sx={{ fontVariantNumeric: 'tabular-nums' }}>
      {value}
    </Typography>
  </Stack>
);

export default function RightDrawer({ symbol, open, onClose }: Props) {
  const enabled = Boolean(open && symbol);
  const { data, isFetching, error } = useInstrumentDetail(symbol || '', undefined, {
    enabled,
    staleTimeMs: 60_000,
  });

  // Read defensively; backend evolved to nested structures.
  const d = (data as DrawerDetail | undefined) as any;
  const ind = d?.indicators || {};
  const meters = d?.meters || {};
  const pos = d?.position || {};
  const na = d?.next_action || {};
  const refs = na?.refs || {};

  /* Effective entry rule:
     - if entry_price_locked>0 use that
     - else if entry_price>0 use that
     - else fall back to suggested entry (if present) or current price
  */
  const locked = typeof pos?.entry_price_locked === 'number' && pos.entry_price_locked > 0;
  const effectiveEntry =
    (locked ? pos.entry_price_locked : pos?.entry_price) ??
    refs?.entry_suggested ??
    d?.price;

  // Trade toggle local UI (no network POST here yet)
  const [tradeOn, setTradeOn] = React.useState<boolean>(Boolean(pos?.trade_on));
  const [entryPrice, setEntryPrice] = React.useState<string>(
    typeof effectiveEntry === 'number' ? String(effectiveEntry) : ''
  );
  const [qty, setQty] = React.useState<string>(pos?.qty ? String(pos.qty) : '');

  React.useEffect(() => {
    setTradeOn(Boolean(pos?.trade_on));
    const eff =
      (typeof pos?.entry_price_locked === 'number' && pos.entry_price_locked > 0
        ? pos.entry_price_locked
        : pos?.entry_price) ?? refs?.entry_suggested ?? d?.price;
    setEntryPrice(typeof eff === 'number' ? String(eff) : '');
    setQty(pos?.qty ? String(pos.qty) : '');
  }, [
    d?.price,
    pos?.trade_on,
    pos?.entry_price,
    pos?.entry_price_locked,
    pos?.qty,
    refs?.entry_suggested,
  ]);

  const lockDisabled =
    !tradeOn || !entryPrice || Number(entryPrice) <= 0 || (qty && Number(qty) <= 0);

  // Header helpers
  const pct1d = d?.pct_today ?? d?.change_pct_1d ?? d?.change_pct;
  const pctColor =
    typeof pct1d === 'number' ? (pct1d >= 0 ? 'success.main' : 'error.main') : 'text.secondary';

  // Badges row
  const badges: string[] = Array.isArray(d?.badges) ? d.badges : [];

  return (
    <Drawer anchor="right" open={open} onClose={onClose} PaperProps={{ sx: { width: 520, p: 2 } }}>
      {/* Header */}
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
        <Box>
          <Typography variant="h6" sx={{ fontWeight: 700 }}>
            {d?.name || symbol || '—'}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {d?.sector || '—'}
            {d?.run_id ? ` · Run ${d.run_id}` : d?.resolved_run_id ? ` · Run ${d.resolved_run_id}` : ''}
          </Typography>
        </Box>
        <Box textAlign="right">
          <Typography variant="h6" sx={{ fontVariantNumeric: 'tabular-nums' }}>
            {rup(d?.price)}
          </Typography>
          <Typography
            variant="body2"
            sx={{
              color: pctColor,
              fontWeight: 700,
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            {pct(pct1d)}
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

      {/* Sparkline (30D) placeholder */}
      <Box
        sx={{
          height: 84,
          bgcolor: 'action.hover',
          borderRadius: 1,
          mb: 2,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 12,
          color: 'text.secondary',
        }}
        title="30D sparkline (wire to data later)"
      >
        Sparkline (30D)
      </Box>

      {/* Indicators */}
      <Box sx={{ mb: 2 }}>
        <Grid container spacing={1.5}>
          <Grid item xs={6}>
            <Field label="RSI(14)" value={num(ind?.rsi14, 1)} />
          </Grid>
          <Grid item xs={6}>
            <Field label="ADX(14)" value={num(ind?.adx14, 1)} />
          </Grid>
          <Grid item xs={6}>
            <Field label={`EMA Fast${ind?.ema_fast ? ` (${ind.ema_fast})` : ''}`} value={num(ind?.ema_fast_value, 2)} />
          </Grid>
          <Grid item xs={6}>
            <Field label={`EMA Slow${ind?.ema_slow ? ` (${ind.ema_slow})` : ''}`} value={num(ind?.ema_slow_value, 2)} />
          </Grid>
          <Grid item xs={6}>
            <Field label="ATR %" value={pct(ind?.atr_pct)} />
          </Grid>
          <Grid item xs={6}>
            <Field label="RelVol(20)" value={relvol(ind?.relvol20)} />
          </Grid>
          <Grid item xs={12}>
            <Field label="vs 52W High" value={prox52w(ind?.proximity_52w_high_pct)} />
          </Grid>
        </Grid>
      </Box>

      {/* Score breakdown */}
      <Box sx={{ mb: 2 }}>
        <Typography variant="subtitle2" sx={{ mb: 1 }}>
          Score Breakdown
        </Typography>
        <BarRow label="Total Score" value={d?.score} />
        {'trend_rank' in (d || {}) && <BarRow label="Trend" value={d?.trend_rank} />}
        {'breakout_quality' in (d || {}) && <BarRow label="Breakout Quality" value={d?.breakout_quality} />}
        {'relvol' in (d || {}) && <BarRow label="Accumulation / RelVol" value={d?.relvol} />}
      </Box>

      {/* Meters */}
      <Box sx={{ mb: 2 }}>
        <Typography variant="subtitle2" sx={{ mb: 1 }}>
          Meters
        </Typography>
        <Grid container spacing={1.5}>
          <Grid item xs={6}>
            <LevelChip label="Risk" level={meters?.risk?.level} basis={meters?.risk?.basis} />
          </Grid>
          <Grid item xs={6}>
            <LevelChip label="Euphoria" level={meters?.euphoria?.level} basis={meters?.euphoria?.basis} />
          </Grid>
        </Grid>
      </Box>

      {/* Next Action */}
      <Box sx={{ mb: 2 }}>
        <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
          Next Action
        </Typography>
        <Typography variant="body2" sx={{ fontWeight: 600 }}>
          {na?.text || na?.reason || na?.state || '—'}
        </Typography>
        {/* Inline refs: compact numeric hints when available */}
        <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 0.5, color: 'text.secondary' }}>
          {typeof refs?.ema_n === 'number' && typeof refs?.ema_value === 'number' ? (
            <Chip size="small" variant="outlined" label={`EMA${refs.ema_n}=${num(refs.ema_value, 2)}`} />
          ) : null}
          {typeof refs?.entry_suggested === 'number' ? (
            <Chip size="small" variant="outlined" label={`Suggested Entry ${rup(refs.entry_suggested)}`} />
          ) : null}
          {d?.method_pill ? <Chip size="small" color="default" label={d.method_pill} /> : null}
        </Stack>
      </Box>

      {/* Entry module */}
      <Box sx={{ mb: 2 }}>
        <Typography variant="subtitle2" sx={{ mb: 1 }}>
          Entry
        </Typography>

        <KV
          label="Entry price"
          value={rup(effectiveEntry)}
          help={locked ? 'Locked' : 'Suggested (can lock when Trade ON)'}
        />

        <Stack direction="row" alignItems="center" spacing={1} sx={{ mt: 1, mb: 1 }}>
          <Switch
            checked={tradeOn}
            onChange={(e) => setTradeOn(e.target.checked)}
            inputProps={{ 'aria-label': 'Trade toggle' }}
          />
          <Typography variant="body2">Trade</Typography>
          {locked && (
            <Tooltip title="Entry is locked; adjust via dedicated flow">
              <InfoOutlinedIcon fontSize="small" />
            </Tooltip>
          )}
        </Stack>

        {tradeOn && (
          <Stack direction="row" spacing={1} sx={{ mb: 1, flexWrap: 'wrap' }}>
            <TextField
              size="small"
              label="Entry price (₹)"
              value={entryPrice}
              onChange={(e) => setEntryPrice(e.target.value)}
              sx={{ width: 180 }}
              inputProps={{ inputMode: 'decimal' }}
              disabled={locked}
            />
            <TextField
              size="small"
              label="Qty"
              value={qty}
              onChange={(e) => setQty(e.target.value)}
              sx={{ width: 120 }}
              inputProps={{ inputMode: 'numeric' }}
              disabled={locked}
            />
            <Button variant="contained" disabled={lockDisabled || locked}>
              Lock entry
            </Button>
          </Stack>
        )}

        {/* Action block (computed on backend using effective entry) */}
        <Stack spacing={0.5} sx={{ mt: 1 }}>
          <KV label="Stop-loss (now)" value={typeof pos?.stop_now === 'number' ? rup(pos?.stop_now) : '—'} help="sell if touched" />
          <KV
            label="Exit at close if"
            value={typeof pos?.exit_close_threshold === 'number' ? `Close < ${rup(pos?.exit_close_threshold)}` : '—'}
            help="sell next day if true"
          />
          <KV
            label="Breakeven"
            value={pos?.breakeven_active ? 'Active' : 'Pending'}
            help="stop won’t go below entry"
          />
          <KV label="Euphoria" value={pos?.euphoria_on ? 'On' : 'Off'} help="tighter stop & faster EMA" />
        </Stack>
      </Box>

      {/* Alerts */}
      <Box sx={{ mb: 2 }}>
        <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
          Alerts
        </Typography>
        <Stack direction="row" spacing={1} alignItems="center" sx={{ flexWrap: 'wrap' }}>
          {/* Render templates if present, else show common presets */}
          {Array.isArray(d?.alert_templates) && d.alert_templates.length > 0
            ? d.alert_templates.map((t: any, i: number) => (
                <Chip key={`alert-${i}`} icon={<NotificationsActiveIcon />} label={String(t?.label ?? 'Alert')} variant="outlined" />
              ))
            : [
                'Price crosses ₹X',
                'Enters breakout',
                'Close < EMAₙ',
                'Breakeven active',
                'Stop hit',
              ].map((lbl) => (
                <Chip key={lbl} icon={<NotificationsActiveIcon />} label={lbl} variant="outlined" />
              ))}
        </Stack>
      </Box>

      {/* Footer */}
      <Divider sx={{ my: 1.5 }} />
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
        {d?.as_of ? `As of ${new Date(d.as_of).toLocaleString()}` : ''}
        {isFetching ? ' · refreshing…' : ''}
        {d?.symbol_canon ? ` · ${d.symbol_canon}` : ''}
      </Typography>

      {error ? (
        <Typography variant="body2" color="error" sx={{ mt: 1 }}>
          {(error as any)?.message || 'Failed to load details.'}
        </Typography>
      ) : null}
    </Drawer>
  );
}
