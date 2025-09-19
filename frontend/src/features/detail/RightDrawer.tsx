import * as React from 'react';
import {
  Drawer, Box, Typography, Chip, Divider, Grid, Tooltip,
  IconButton, Button, Stack, TextField, Switch, Avatar, LinearProgress
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import WhatshotIcon from '@mui/icons-material/Whatshot';
import SpeedIcon from '@mui/icons-material/Speed';
import NotificationsActiveIcon from '@mui/icons-material/NotificationsActive';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import type { DrawerDetail } from '@/lib/api/types';
import { useInstrumentDetail } from '@/lib/hooks';
import { drawerPaperSx, sectionDividerSx } from './styles';

/** ----- Formatters ----- */
const pct = (v?: number, d = 2) => (typeof v === 'number' && isFinite(v) ? `${v.toFixed(d)}%` : '—');
const rup = (v?: number, d = 2) => (typeof v === 'number' && isFinite(v) ? `₹${v.toFixed(d)}` : '—');
const num = (v?: number, d = 2) => (typeof v === 'number' && isFinite(v) ? v.toFixed(d) : '—');
const relvol = (v?: number) => (typeof v === 'number' && isFinite(v) ? `${v.toFixed(2)}×` : '—');
const prox52w = (p?: number) => {
  if (typeof p !== 'number' || !isFinite(p)) return '—';
  return p === 0 ? 'At 52W high' : p > 0 ? `${pct(p)} above` : `${pct(Math.abs(p))} below`;
};
const levelColor = (s?: string) => {
  switch ((s || '').toLowerCase()) {
    case 'low': return 'success';
    case 'medium': return 'warning';
    case 'high': return 'error';
    default: return 'default';
  }
};

/** ----- Small atoms ----- */
const Row: React.FC<{ label: string; value: React.ReactNode; hint?: string }> = ({ label, value, hint }) => (
  <Stack direction="row" alignItems="baseline" spacing={1} sx={{ minWidth: 0 }}>
    <Typography variant="body2" sx={{ width: 100, color: 'text.secondary', flexShrink: 0 }}>{label}:</Typography>
    <Typography variant="body2" sx={{ fontVariantNumeric: 'tabular-nums' }}>{value}</Typography>
    {hint ? <Typography variant="caption" color="text.secondary">— {hint}</Typography> : null}
  </Stack>
);

const MeterChip: React.FC<{ icon: React.ReactNode; label: string; level?: string; basis?: Record<string, number> }> = ({
  icon, label, level, basis,
}) => {
  const title = basis && Object.keys(basis).length
    ? Object.entries(basis).map(([k, v]) => `${k}: ${typeof v === 'number' ? v.toFixed(2) : v}`).join(' · ')
    : '';
  return (
    <Stack direction="row" spacing={1} alignItems="center">
      {icon}
      <Tooltip title={title} disableHoverListener={!title}>
        <Chip size="small" color={levelColor(level) as any} variant="filled" label={`${label}: ${level ?? '—'}`} />
      </Tooltip>
    </Stack>
  );
};

type Props = { symbol: string | null; open: boolean; onClose: () => void };

export default function RightDrawer({ symbol, open, onClose }: Props) {
  const enabled = Boolean(open && symbol);
  const { data, isFetching, error } = useInstrumentDetail(symbol || '', undefined, {
    enabled,
    staleTimeMs: 60_000,
  });

  // Defensive read
  const d = (data as DrawerDetail | undefined) as any;
  const ind = d?.indicators || {};
  const meters = d?.meters || {};
  const pos = d?.position || {};
  const na = d?.next_action || {};
  const refs = na?.refs || {};

  /** Effective entry precedence (frozen):
   * locked > entry > suggested > price
   */
  const locked = typeof pos?.entry_price_locked === 'number' && pos.entry_price_locked > 0;
  const effectiveEntry =
    (locked ? pos.entry_price_locked : pos?.entry_price) ?? refs?.entry_suggested ?? d?.price;

  // Local UI state (view-only flow; no POST wiring here)
  const [tradeOn, setTradeOn] = React.useState<boolean>(Boolean(pos?.trade_on));
  const [entryPrice, setEntryPrice] = React.useState<string>(typeof effectiveEntry === 'number' ? String(effectiveEntry) : '');
  const [qty, setQty] = React.useState<string>(pos?.qty ? String(pos.qty) : '');
  React.useEffect(() => {
    setTradeOn(Boolean(pos?.trade_on));
    const eff =
      (typeof pos?.entry_price_locked === 'number' && pos.entry_price_locked > 0 ? pos.entry_price_locked : pos?.entry_price) ??
      refs?.entry_suggested ?? d?.price;
    setEntryPrice(typeof eff === 'number' ? String(eff) : '');
    setQty(pos?.qty ? String(pos.qty) : '');
  }, [d?.price, pos?.trade_on, pos?.entry_price, pos?.entry_price_locked, pos?.qty, refs?.entry_suggested]);
  const lockDisabled = !tradeOn || !entryPrice || Number(entryPrice) <= 0 || (qty && Number(qty) <= 0);

  const pct1d = d?.pct_today ?? d?.change_pct_1d ?? d?.change_pct;
  const pctColor = typeof pct1d === 'number' ? (pct1d >= 0 ? 'success' : 'error') : 'default';
  const badges: string[] = Array.isArray(d?.badges) ? d.badges : [];
  // valid MUI chip colors
const muiColors = new Set(['default','primary','secondary','success','info','warning','error']);
const normBadge = (b: any) => {
  if (b == null) return { label: '—', color: 'default' as const };
  if (typeof b === 'string' || typeof b === 'number') return { label: String(b), color: 'default' as const };
  // object shape from backend: {code, text, key, label, color}
  const label =
    (b.label && String(b.label)) ||
    (b.text && String(b.text)) ||
    (b.code && String(b.code)) ||
    (b.key && String(b.key)) ||
    'Badge';
  const color = muiColors.has(String(b.color)) ? (b.color as any) : 'default';
  return { label, color };
};


  return (
    <Drawer anchor="right" open={open} onClose={onClose} PaperProps={{ sx: drawerPaperSx }}>
      {/* HEADER */}
      <Box sx={{ position: 'sticky', top: 0, zIndex: 2, px: 3, py: 1.25, bgcolor: 'background.paper', borderBottom: 1, borderColor: 'divider' }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" spacing={2}>
          <Stack direction="row" spacing={1.25} alignItems="center" sx={{ minWidth: 0 }}>
            <Avatar sx={{ width: 28, height: 28, bgcolor: 'primary.main', fontSize: 14 }}>
              {(d?.symbol_canon || d?.name || symbol || '—').slice(0, 2).toUpperCase()}
            </Avatar>
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="h6" noWrap title={d?.name || symbol || '—'}>{d?.name || symbol || '—'}</Typography>
              <Typography variant="caption" color="text.secondary" noWrap title={d?.sector || ''}>
                {(d?.sector || '—')}{d?.run_id ? ` · Run ${d.run_id}` : d?.resolved_run_id ? ` · Run ${d.resolved_run_id}` : ''}
              </Typography>
            </Box>
          </Stack>

          <Stack spacing={0.25} alignItems="flex-end" sx={{ flexShrink: 0 }}>
            <Typography variant="h6" sx={{ fontVariantNumeric: 'tabular-nums' }}>{rup(d?.price)}</Typography>
            <Chip size="small" color={pctColor as any} label={pct(pct1d)} variant="filled" />
          </Stack>

          <IconButton onClick={onClose} aria-label="close" sx={{ flexShrink: 0 }}>
            <CloseIcon />
          </IconButton>
        </Stack>

        {/* Badges row */}

        <Stack direction="row" spacing={1} sx={{ mt: 1, flexWrap: 'wrap' }}>
          <Chip size="small" color="secondary" variant="filled" label={`Score: ${num(d?.score)}`} />
          {d?.method_pill ? <Chip size="small" color="info" variant="filled" label={String(d.method_pill)} /> : null}
          <Chip size="small" variant="outlined" label={`52W: ${prox52w(ind?.proximity_52w_high_pct)}`} />

          {Array.isArray(d?.badges)
            ? d.badges.slice(0, 6).map((raw: any, i: number) => {
                const b = normBadge(raw);
                return (
                  <Chip
                    key={`badge-${i}`}
                    size="small"
                    variant={b.color === 'default' ? 'outlined' : 'filled'}
                    color={b.color as any}
                    label={b.label}
                  />
                );
              })
            : null}
        </Stack>

      </Box>

      {/* BODY CANVAS */}
      <Box sx={{ px: 3, py: 2, overflowY: 'auto', '& *': { minWidth: 0 } }}>
        {/* 2) Sparkline (placeholder) */}
        <Box sx={{ mb: 2 }}>
          <Typography variant="subtitle2" sx={{ mb: .75 }}>Sparkline (30D)</Typography>
          <Box sx={{ height: 170, borderRadius: 2, bgcolor: '#0c1529', border: 1, borderColor: 'divider', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'text.secondary', fontSize: 12 }}>
            Sparkline (30D)
          </Box>
        </Box>

        {/* 3) Indicators grid */}
        <Box sx={{ mb: 2 }}>
          <Typography variant="subtitle2" sx={{ mb: .75 }}>Indicators</Typography>
          <Divider sx={sectionDividerSx} />
          <Grid container spacing={1.25} sx={{ mt: 1 }}>
            <Grid item xs={12} sm={6}><Row label="RSI(14)" value={num(ind?.rsi14, 1)} /></Grid>
            <Grid item xs={12} sm={6}><Row label="ADX(14)" value={num(ind?.adx14, 1)} /></Grid>
            <Grid item xs={12} sm={6}><Row label={`EMA Fast${ind?.ema_fast ? ` (${ind.ema_fast})` : ''}`} value={num(ind?.ema_fast_value, 2)} /></Grid>
            <Grid item xs={12} sm={6}><Row label={`EMA Slow${ind?.ema_slow ? ` (${ind.ema_slow})` : ''}`} value={num(ind?.ema_slow_value, 2)} /></Grid>
            <Grid item xs={12} sm={6}><Row label="ATR %" value={pct(ind?.atr_pct)} /></Grid>
            <Grid item xs={12} sm={6}><Row label="RelVol(20)" value={relvol(ind?.relvol20)} /></Grid>
            <Grid item xs={12}><Row label="vs 52W High" value={prox52w(ind?.proximity_52w_high_pct)} /></Grid>
          </Grid>
        </Box>

        {/* 4) Score breakdown */}
        <Box sx={{ mb: 2 }}>
          <Typography variant="subtitle2" sx={{ mb: .75 }}>Score Breakdown</Typography>
          <Divider sx={sectionDividerSx} />
          <Stack spacing={1.25} sx={{ mt: 1 }}>
            <Stack>
              <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5 }}>Total Score</Typography>
              <Stack direction="row" spacing={1} alignItems="center">
                <Box sx={{ flex: 1 }}>
                  <LinearProgress
                    variant="determinate"
                    value={typeof d?.score === 'number' ? Math.max(0, Math.min(100, d.score)) : 0}
                    sx={{ height: 10, borderRadius: 999 }}
                  />
                </Box>
                <Typography variant="body2" sx={{ width: 36, textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                  {typeof d?.score === 'number' ? Math.round(d.score) : '—'}
                </Typography>
              </Stack>
            </Stack>
            {'trend_rank' in (d || {}) && (
              <Stack>
                <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5 }}>Trend</Typography>
                <LinearProgress variant="determinate" value={Math.max(0, Math.min(100, Number(d?.trend_rank) || 0))} sx={{ height: 8, borderRadius: 999 }} />
              </Stack>
            )}
            {'breakout_quality' in (d || {}) && (
              <Stack>
                <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5 }}>Breakout Quality</Typography>
                <LinearProgress variant="determinate" value={Math.max(0, Math.min(100, Number(d?.breakout_quality) || 0))} sx={{ height: 8, borderRadius: 999 }} />
              </Stack>
            )}
            {'relvol' in (d || {}) && (
              <Stack>
                <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5 }}>Accumulation / RelVol</Typography>
                <LinearProgress variant="determinate" value={Math.max(0, Math.min(100, Number(d?.relvol) || 0))} sx={{ height: 8, borderRadius: 999 }} />
              </Stack>
            )}
          </Stack>
        </Box>

        {/* 5) Entry (suggested / locked) */}
        <Box sx={{ mb: 2 }}>
          <Typography variant="subtitle2" sx={{ mb: .75 }}>Entry</Typography>
          <Divider sx={sectionDividerSx} />
          <Stack spacing={0.75} sx={{ mt: 1 }}>
            <Row label="Entry price" value={rup(effectiveEntry)} hint={locked ? 'Locked' : (refs?.entry_reason || 'Suggested')} />
            {/* One-line rationale (text or reasons[0]) */}
            {na?.text ? (
              <Typography variant="caption" color="text.secondary">
                {refs?.entry_reason || na?.refs?.entry_reason || (Array.isArray(na?.reasons) ? na.reasons.join(' · ') : '')}
              </Typography>
            ) : null}
          </Stack>
        </Box>

        {/* 6) Trade toggle & Lock entry (inline) */}
        <Box sx={{ mb: 2 }}>
          <Stack direction="row" alignItems="center" spacing={1.25}>
            <Switch checked={tradeOn} onChange={(e) => setTradeOn(e.target.checked)} />
            <Typography variant="body2">Trade</Typography>
            {locked && <Tooltip title="Entry is locked; adjust via dedicated flow"><InfoOutlinedIcon fontSize="small" /></Tooltip>}
          </Stack>
          {tradeOn && (
            <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', mt: 1 }}>
              <TextField
                size="small"
                label="Entry price (₹)"
                value={entryPrice}
                onChange={(e) => setEntryPrice(e.target.value)}
                sx={{ width: 220 }}
                inputProps={{ inputMode: 'decimal' }}
                disabled={locked}
              />
              <TextField
                size="small"
                label="Qty"
                value={qty}
                onChange={(e) => setQty(e.target.value)}
                sx={{ width: 160 }}
                inputProps={{ inputMode: 'numeric' }}
                disabled={locked}
              />
              <Button variant="contained" disabled={lockDisabled || locked}>Lock entry</Button>
            </Stack>
          )}
        </Box>

        {/* 7) Action block */}
        <Box sx={{ mb: 2 }}>
          <Typography variant="subtitle2" sx={{ mb: .75 }}>Action</Typography>
          <Divider sx={sectionDividerSx} />
          <Stack spacing={0.75} sx={{ mt: 1 }}>
            <Row label="Stop-loss (now)" value={typeof pos?.stop_now === 'number' ? rup(pos?.stop_now) : '—'} hint="sell if touched" />
            <Row
              label="Exit at close if"
              value={typeof pos?.exit_close_threshold === 'number' ? `Close < ${rup(pos?.exit_close_threshold)}` : '—'}
              hint="sell next day if true"
            />
            <Row label="Breakeven" value={pos?.breakeven_active ? 'Active' : 'Pending'} hint="stop won’t go below entry" />
            <Row label="Euphoria" value={pos?.euphoria_on ? 'On' : 'Off'} hint="tighter stop & faster EMA" />
            {d?.method_pill ? <Chip size="small" color="info" variant="filled" label={d.method_pill} /> : null}
          </Stack>
        </Box>

        {/* 8) Meters */}
        <Box sx={{ mb: 2 }}>
          <Typography variant="subtitle2" sx={{ mb: .75 }}>Meters</Typography>
          <Divider sx={sectionDividerSx} />
          <Stack direction="row" spacing={1.25} sx={{ flexWrap: 'wrap', mt: 1 }}>
            <MeterChip icon={<SpeedIcon fontSize="small" />} label="Risk" level={meters?.risk?.level} basis={meters?.risk?.basis} />
            <MeterChip icon={<WhatshotIcon fontSize="small" />} label="Euphoria" level={meters?.euphoria?.level} basis={meters?.euphoria?.basis} />
          </Stack>
        </Box>

        {/* 9) Next Action (single line) */}
        <Box sx={{ mb: 2 }}>
          <Typography variant="subtitle2" sx={{ mb: .75 }}>Next Action</Typography>
          <Divider sx={sectionDividerSx} />
          <Stack spacing={0.5} sx={{ mt: 1 }}>
            <Typography variant="body2" sx={{ fontWeight: 700 }}>
              {na?.text || na?.reason || na?.state || '—'}
            </Typography>
            <Stack direction="row" spacing={1} alignItems="center" sx={{ flexWrap: 'wrap', color: 'text.secondary' }}>
              {typeof refs?.ema_n === 'number' && typeof refs?.ema_value === 'number' ? (
                <Chip size="small" variant="filled" label={`EMA${refs.ema_n}=${num(refs.ema_value, 2)}`} />
              ) : null}
              {typeof refs?.entry_suggested === 'number' ? (
                <Chip size="small" variant="filled" label={`Suggested Entry ${rup(refs.entry_suggested)}`} />
              ) : null}
              {typeof refs?.entry_low === 'number' && typeof refs?.entry_high === 'number' ? (
                <Chip size="small" variant="filled" label={`Entry Band ${rup(refs.entry_low)}–${rup(refs.entry_high)}`} />
              ) : null}
              {refs?.entry_type ? <Chip size="small" variant="filled" label={String(refs.entry_type)} /> : null}
              {d?.method_pill ? <Chip size="small" color="info" variant="filled" label={d.method_pill} /> : null}
            </Stack>
          </Stack>
        </Box>

        {/* 10) Alerts */}
        <Box sx={{ mb: 2 }}>
          <Typography variant="subtitle2" sx={{ mb: .75 }}>Alerts</Typography>
          <Divider sx={sectionDividerSx} />
          <Stack direction="row" spacing={1} alignItems="center" sx={{ flexWrap: 'wrap', mt: 1 }}>
            {Array.isArray(d?.alert_templates) && d.alert_templates.length > 0
              ? d.alert_templates.map((t: any, i: number) => (
                  <Chip key={`alert-${i}`} icon={<NotificationsActiveIcon />} label={String(t?.label ?? 'Alert')} variant="outlined" />
                ))
              : ['Price crosses ₹X','Enters breakout','Close < EMAₙ','Breakeven active','Stop hit'].map((lbl) => (
                  <Chip key={lbl} icon={<NotificationsActiveIcon />} label={lbl} variant="outlined" />
                ))}
          </Stack>
        </Box>

        {/* 11) Footer */}
        <Divider sx={{ my: 2 }} />
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', pb: 1 }}>
          {d?.as_of ? `As of ${new Date(d.as_of).toLocaleString()}` : ''}
          {isFetching ? ' · refreshing…' : ''}
          {d?.run_id ? ` · Run ${d.run_id}` : d?.resolved_run_id ? ` · Run ${d.resolved_run_id}` : ''}
          {d?.symbol_canon ? ` · ${d.symbol_canon}` : ''}
        </Typography>

        {error ? (
          <Typography variant="body2" color="error" sx={{ mt: 1, pb: 2 }}>
            {(error as any)?.message || 'Failed to load details.'}
          </Typography>
        ) : null}
      </Box>
    </Drawer>
  );
}
