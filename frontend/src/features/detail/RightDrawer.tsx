// detail/RightDrawer.tsx
import * as React from 'react';
import {
  Drawer,
  Box,
  Typography,
  Divider,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
} from '@mui/material';
import type { DrawerDetail } from '@/lib/api/types';
import { useInstrumentDetail, usePosition, useLockPosition, useUnlockPosition } from '@/lib/hooks';
import { drawerPaperSx } from './styles';

import DrawerHeader from './DrawerHeader';
import Sparkline from './SparklineRe';
import IndicatorsGrid from './IndicatorsGrid';
import ScoreBreakdown from './ScoreBreakdown';
import EntryModule from './EntryModule';
import ActionBlock from './StopLossAction';
import Meters from './Meters';
import NextAction from './NextAction';
import AlertsRow from './AlertsRow';

type Props = { symbol: string | null; open: boolean; onClose: () => void };

function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <Box sx={{ mt: 2, mb: 1 }}>
      <Typography
        variant="overline"
        sx={{
          fontWeight: 800,
          letterSpacing: '.12em',
          textTransform: 'uppercase',
          color: 'text.secondary',
        }}
      >
        {children}
      </Typography>
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
  const sym = symbol || '';
  const enabled = Boolean(open && sym);

  const { data, isFetching, error, refetch: refetchDetail } = useInstrumentDetail(
    sym,
    undefined,
    { enabled, staleTimeMs: 60_000 }
  );

  const { data: position, refetch: refetchPosition } = usePosition(sym, { enabled });

  const d = (data as DrawerDetail | undefined) as any;
  const header = d?.header || {};
  const ind = d?.indicators || {};
  const meters = d?.meters || {};
  const posFromDetail = d?.position || {};
  const sb = d?.score_breakdown || {};
  const ab = d?.action_block || {};
  const na = d?.next_action || {};
  const refs = na?.refs || {};

  const pctToday =
    header?.pct_1d ?? d?.pct_today ?? d?.change_pct_1d ?? d?.change_pct;
  const runId = d?.run_id ?? d?.resolved_run_id;

  const normalizeBadgeLabel = (b: any): string =>
    String(b?.label ?? b?.text ?? b?.code ?? (typeof b === 'number' ? b : b ?? ''));
  const badges: string[] = (Array.isArray(header?.badges) ? header.badges : Array.isArray(d?.badges) ? d.badges : [])
    .map(normalizeBadgeLabel)
    .filter(Boolean)
    .slice(0, 6);

  // ---- Prefer live /positions/{symbol} ----
  const lockedFromPosition =
    typeof position?.entry_price_locked === 'number' && position.entry_price_locked > 0;
  const lockedFromDetail =
    typeof posFromDetail?.entry_price_locked === 'number' && posFromDetail.entry_price_locked > 0;
  const locked = lockedFromPosition || lockedFromDetail;

  const rawEffectiveEntry = lockedFromPosition
    ? (position!.entry_price_locked as number)
    : lockedFromDetail
    ? (posFromDetail.entry_price_locked as number)
    : (refs?.entry_suggested ?? header?.price ?? d?.price);

  const roundedEffectiveEntry =
    typeof rawEffectiveEntry === 'number' ? Number(rawEffectiveEntry.toFixed(2)) : undefined;

  const qtyServer =
    typeof position?.qty === 'number'
      ? position?.qty
      : typeof posFromDetail?.qty === 'number'
      ? posFromDetail.qty
      : undefined;

  const tradeOnServer =
    typeof position?.trade_on === 'boolean'
      ? position.trade_on
      : Boolean(posFromDetail?.trade_on);

  // 👉 helper to compute a clean suggested price (2 dp)
  const computeSuggestedPriceStr = React.useCallback(() => {
    const s = refs?.entry_suggested ?? header?.price ?? d?.price;
    if (typeof s === 'number' && !Number.isNaN(s)) return Number(s).toFixed(2);
    return '';
  }, [refs?.entry_suggested, header?.price, d?.price]);

  // Local UI state
  const [tradeOn, setTradeOn] = React.useState<boolean>(tradeOnServer);
  const [entryPrice, setEntryPrice] = React.useState<string>(
    typeof roundedEffectiveEntry === 'number' ? roundedEffectiveEntry.toFixed(2) : computeSuggestedPriceStr()
  );
  const [qtyLocal, setQtyLocal] = React.useState<string>(
    typeof qtyServer === 'number' ? String(qtyServer) : ''
  );

  // ⛳ gate to ignore sync effect while unlocking/refetching
  const unlockingRef = React.useRef(false);

  // keep in sync with server responses
  React.useEffect(() => {
    if (unlockingRef.current) return; // ignore during unlock window
    setTradeOn(tradeOnServer);
    setEntryPrice(
      typeof roundedEffectiveEntry === 'number' ? roundedEffectiveEntry.toFixed(2) : computeSuggestedPriceStr()
    );
    setQtyLocal(typeof qtyServer === 'number' ? String(qtyServer) : '');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    tradeOnServer,
    roundedEffectiveEntry,
    qtyServer,
    position?.entry_price_locked,
    posFromDetail?.entry_price_locked,
    position?.qty,
    posFromDetail?.qty,
    computeSuggestedPriceStr,
  ]);

  const breakeven_active =
    String(ab?.breakeven_state || '').toUpperCase() === 'ACTIVE';
  const euphoria_on = String(ab?.euphoria_state || '').toUpperCase() === 'ON';

  const alertTemplates = Array.isArray(d?.alert_templates)
    ? d.alert_templates.map((t: any) => ({
        label: t?.label ?? t?.code ?? t?.example ?? 'Alert',
      }))
    : [];

  const lockMut = useLockPosition();
  const unlockMut = useUnlockPosition();
  const [askConfirm, setAskConfirm] = React.useState(false);

  async function lockNow() {
    const px =
      entryPrice && !Number.isNaN(+entryPrice) && +entryPrice > 0
        ? Number(parseFloat(entryPrice).toFixed(2))
        : (roundedEffectiveEntry as number | undefined);

    if (!sym || !px) return;

    await lockMut.mutateAsync({
      data: {
        symbol: sym,
        price: px,
        as_of: new Date().toISOString(),
        qty: qtyLocal ? Number(qtyLocal) : undefined,
      },
    });

    await Promise.all([refetchPosition(), refetchDetail()]);
  }

  async function unlockNow() {
    const id = position?.id ?? posFromDetail?.id;
    if (!id) {
      setAskConfirm(false);
      return;
    }

    // Optimistic local clear + pause sync while refetch catches up
    unlockingRef.current = true;
    setTradeOn(false);
    setEntryPrice(computeSuggestedPriceStr()); // reset to clean suggestion
    setQtyLocal('');                            // clear qty

    await unlockMut.mutateAsync({ id });
    setAskConfirm(false);

    await Promise.all([refetchPosition(), refetchDetail()]);

    // allow sync again
    unlockingRef.current = false;
  }

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{
        sx: {
          ...drawerPaperSx,
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
        <Sparkline data={d?.sparkline as any} height={200} />

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
            typeof roundedEffectiveEntry === 'number' ? roundedEffectiveEntry : undefined
          }
          locked={locked}
          trade_on={tradeOn}
          qty={qtyServer ?? undefined}
          // do NOT auto-lock on toggle
          onTradeChange={(on) => {
            if (on) {
              setTradeOn(true);
              // if turning on with empty entry, seed suggestion (2 dp)
              if (!entryPrice) setEntryPrice(computeSuggestedPriceStr());
            } else {
              if (locked) setAskConfirm(true);
              else setTradeOn(false);
            }
          }}
          onEntryChange={(v) => {
            const cleaned =
              v && !Number.isNaN(+v) ? Number(parseFloat(v).toFixed(2)).toString() : v;
            setEntryPrice(cleaned);
          }}
          onQtyChange={(v) => setQtyLocal(v)}
          // hide any internal “Lock Entry” button inside EntryModule
          showLockEntryButton={false}
        />

        {/* Only show our explicit Lock button when trade is ON but not yet locked */}
        {tradeOn && !locked && (
          <Box sx={{ display: 'flex', gap: 1, mt: 1 }}>
            <Button variant="contained" onClick={lockNow}>
              Lock trade
            </Button>
            <Button
              variant="outlined"
              onClick={() => {
                // cancel staging (turn off without API)
                setTradeOn(false);
              }}
            >
              Cancel
            </Button>
          </Box>
        )}

        <NextAction
          text={na?.text || na?.reason || na?.state}
          refs={refs}
          method_pill={d?.method_pill}
        />

        <ActionBlock
          stop_now={ab?.stop_now ?? posFromDetail?.stop_now}
          exit_close_threshold={
            ab?.exit_close_threshold ?? posFromDetail?.exit_close_threshold
          }
          breakeven_active={breakeven_active}
          euphoria_on={euphoria_on}
        />

        <SectionHeader>Meters</SectionHeader>
        <Meters risk={meters?.risk} euphoria={meters?.euphoria} />

        <SectionHeader>Alerts</SectionHeader>
        <AlertsRow templates={alertTemplates} />

        <Box sx={{ color: 'text.secondary', fontSize: 12, mt: 2, pb: 1 }}>
          {d?.as_of || header?.as_of ? `As of ${new Date(d?.as_of ?? header?.as_of).toLocaleString()}` : ''}
          {isFetching ? ' · refreshing…' : ''}
          {d?.trading_day ? ` · ${d.trading_day}` : ''}
          {runId ? ` · Run ${runId}` : ''}
          {d?.symbol_canon ? ` · ${d.symbol_canon}` : ''}
          {error ? ` · ${(error as any)?.message || 'Failed to load details.'}` : ''}
        </Box>
      </Box>

      {/* Unlock confirmation */}
      <Dialog open={askConfirm} onClose={() => setAskConfirm(false)}>
        <DialogTitle>Unlock trade?</DialogTitle>
        <DialogContent>
          Unlocking will clear the locked entry price for {sym}. Are you sure?
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAskConfirm(false)}>Cancel</Button>
          <Button onClick={unlockNow} variant="contained" color="error">
            Unlock
          </Button>
        </DialogActions>
      </Dialog>
    </Drawer>
  );
}
