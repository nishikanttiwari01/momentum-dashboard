// detail/RightDrawer.tsx
import * as React from 'react';
import { Drawer, Box, Typography, Divider } from '@mui/material';
import type { DrawerDetail } from '@/lib/api/types';
import { useInstrumentDetail } from '@/lib/hooks';
import { drawerPaperSx } from './styles';

// modular pieces
import DrawerHeader from './DrawerHeader';
import Sparkline from './Sparkline';
import IndicatorsGrid from './IndicatorsGrid';
import ScoreBreakdown from './ScoreBreakdown';
import EntryModule from './EntryModule';
import ActionBlock from './ActionBlock';
import Meters from './Meters';
import NextAction from './NextAction';
import AlertsRow from './AlertsRow';

type Props = { symbol: string | null; open: boolean; onClose: () => void };

/** Minimal, attractive section header (no layout changes) */
function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <Box sx={{ mt: 2, mb: 1 }}>
      <Typography
        variant="overline"
        sx={{
          fontWeight: 800,
          letterSpacing: '.12em',
          textTransform: 'uppercase',
          color: 'text.secondary',     // neutral text (not a blue pill)
        }}
      >
        {children}
      </Typography>

      {/* thin gradient underline (purple → vermilion), not a pill */}
      <Box
        sx={{
          mt: 0.5,
          height: 3,
          borderRadius: 2,
          background: 'linear-gradient(90deg, #7C4DFF 0%, #0b0b0bff 100%)',
          opacity: 0.6,
        }}
      />
    </Box>
  );
}

export default function RightDrawer({ symbol, open, onClose }: Props) {
  const enabled = Boolean(open && symbol);
  const { data, isFetching, error } = useInstrumentDetail(symbol || '', undefined, {
    enabled,
    staleTimeMs: 60_000,
  });

  // tolerate partial shapes
  const d = (data as DrawerDetail | undefined) as any;
  const header = d?.header || {};
  const ind = d?.indicators || {};
  const meters = d?.meters || {};
  const pos = d?.position || {};
  const sb = d?.score_breakdown || {};
  const ab = d?.action_block || {};
  const na = d?.next_action || {};
  const refs = na?.refs || {};

  // ----- normalize fields -----
  const pctToday =
    header?.pct_1d ?? d?.pct_today ?? d?.change_pct_1d ?? d?.change_pct;
  const runId = d?.run_id ?? d?.resolved_run_id;

  const normalizeBadgeLabel = (b: any): string => {
    if (!b) return '';
    if (typeof b === 'string' || typeof b === 'number') return String(b);
    if (b.label) return String(b.label);
    if (b.text) return String(b.text);
    if (b.code) return String(b.code);
    return '';
  };
  const badges: string[] = (Array.isArray(header?.badges)
    ? header.badges
    : Array.isArray(d?.badges)
    ? d.badges
    : []
  )
    .map(normalizeBadgeLabel)
    .filter(Boolean)
    .slice(0, 6);

  // Entry: locked > manual > suggested > market
  const locked =
    typeof pos?.entry_price_locked === 'number' && pos.entry_price_locked > 0;
  const effectiveEntry =
    (locked ? pos.entry_price_locked : pos?.entry_price) ??
    refs?.entry_suggested ??
    (header?.price ?? d?.price);

  // Local view-only state
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
        : pos?.entry_price) ??
      refs?.entry_suggested ??
      (header?.price ?? d?.price);
    setEntryPrice(typeof eff === 'number' ? String(eff) : '');
    setQty(pos?.qty ? String(pos.qty) : '');
  }, [
    header?.price,
    d?.price,
    pos?.trade_on,
    pos?.entry_price,
    pos?.entry_price_locked,
    pos?.qty,
    refs?.entry_suggested,
  ]);

  // map new action_block states to legacy ActionBlock props for display
  const breakeven_active =
    String(ab?.breakeven_state || '').toUpperCase() === 'ACTIVE';
  const euphoria_on = String(ab?.euphoria_state || '').toUpperCase() === 'ON';

  // Alerts: map any shape to {label} for AlertsRow
  const alertTemplates = Array.isArray(d?.alert_templates)
    ? d.alert_templates.map((t: any) => ({
        label: t?.label ?? t?.code ?? t?.example ?? 'Alert',
      }))
    : [];

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{
        sx: {
          ...drawerPaperSx,
          // less shiny: plain surface, no gradients
          backgroundColor: (t) => t.palette.background.paper,
          backgroundImage: 'none',
        },
      }}
    >
      {/* HEADER (sticky) */}
      <Box
        sx={{
          position: 'sticky',
          top: 0,
          zIndex: 2,
          px: 3,
          py: 1.25,
          bgcolor: 'background.paper',
          borderBottom: 1,
          borderColor: 'divider',
        }}
      >
        <DrawerHeader
          name={header?.name ?? d?.name ?? symbol ?? '—'}
          sector={header?.sector ?? d?.sector}
          price={header?.price ?? d?.price}
          pctToday={pctToday}
          runId={runId}
          badges={badges}
          onClose={onClose}
        />
      </Box>

      {/* BODY */}
      <Box sx={{ px: 3, py: 2, overflowY: 'auto' }}>
        {/* Sparkline (fixed: use d?.sparkline instead of undefined detail) */}
        <Sparkline data={d?.sparkline as any} height={150} />

        <ScoreBreakdown
          score={
            typeof sb?.score_total_0_100 === 'number'
              ? sb.score_total_0_100
              : d?.score
          }
          trend_rank={sb?.trend_rank ?? d?.trend_rank}
          breakout_quality={sb?.breakout_quality ?? d?.breakout_quality}
          relvol={sb?.relvol ?? d?.relvol}
        />

        <IndicatorsGrid ind={ind} />

        <EntryModule
          effectiveEntry={
            typeof effectiveEntry === 'number' ? effectiveEntry : undefined
          }
          locked={locked}
          trade_on={tradeOn}
          qty={qty ? Number(qty) : undefined}
          onTradeChange={(on) => setTradeOn(on)}
          onEntryChange={(v) => setEntryPrice(v)}
          onQtyChange={(v) => setQty(v)}
        />

        <NextAction
          text={na?.text || na?.reason || na?.state}
          refs={refs}
          method_pill={d?.method_pill}
        />

        <ActionBlock
          stop_now={ab?.stop_now ?? d?.position?.stop_now}
          exit_close_threshold={
            ab?.exit_close_threshold ?? d?.position?.exit_close_threshold
          }
          breakeven_active={breakeven_active}
          euphoria_on={euphoria_on}
        />

        {/* Meters */}
        <SectionHeader>Meters</SectionHeader>
        <Meters risk={meters?.risk} euphoria={meters?.euphoria} />

        {/* Alerts */}
        <SectionHeader>Alerts</SectionHeader>
        <AlertsRow templates={alertTemplates} />

        {/* Footer */}
        <Box sx={{ color: 'text.secondary', fontSize: 12, mt: 2, pb: 1 }}>
          {d?.as_of || header?.as_of
            ? `As of ${new Date(
                d?.as_of ?? header?.as_of
              ).toLocaleString()}`
            : ''}
          {isFetching ? ' · refreshing…' : ''}
          {d?.trading_day ? ` · ${d.trading_day}` : ''}
          {runId ? ` · Run ${runId}` : ''}
          {d?.symbol_canon ? ` · ${d.symbol_canon}` : ''}
          {error ? ` · ${(error as any)?.message || 'Failed to load details.'}` : ''}
        </Box>
      </Box>
    </Drawer>
  );
}
