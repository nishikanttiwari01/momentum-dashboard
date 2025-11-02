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
  TextField,
  Tabs,
  Tab,
  List,
  ListItem,
  ListItemText,
  Link,
  CircularProgress,
} from '@mui/material';
import CheckCircleRoundedIcon from '@mui/icons-material/CheckCircleRounded';
import CancelRoundedIcon from '@mui/icons-material/CancelRounded';
import type {
  DrawerDetail,
  DrawerDiagnosticsBuyChecklist,
  BuyEvaluation,
  NewsCard,
  AlertTemplate,
} from '@/lib/api/types';
import { useInstrumentDetail, usePosition, useLockPosition, useUnlockPosition, useAllNewsInfinite } from '@/lib/hooks';
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

const checklistHeaderCellSx = {
  fontWeight: 700,
  letterSpacing: '.08em',
  textTransform: 'uppercase',
  color: 'text.secondary',
} as const;

type SelectionMeta = {
  selected: boolean;
  reason?: string | null;
  rMultiple?: number | null;
  stopPrice?: number | null;
  targetPrice?: number | null;
  runId?: string | null;
  tradingDay?: string | null;
};

type Props = {
  symbol: string | null;
  open: boolean;
  onClose: () => void;
  /** Intraday snapshot (when present) */
  runId?: string;
  /** EOD snapshot date (YYYY-MM-DD). Used when runId is not provided. */
  asOf?: string;
};

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

function BuyChecklistSection({
  evaluation,
  selection,
}: {
  evaluation?: BuyEvaluation | null;
  selection?: SelectionMeta | null;
}) {
  if (!evaluation || !Array.isArray(evaluation.checks) || evaluation.checks.length === 0) {
    return null;
  }

  const sanitizeActual = (value: unknown): string => {
    if (value === null || value === undefined) return 'NA';
    let text = String(value).trim();
    text = text.replace(/^(Actual|Value)\s*:\s*/i, '').trim();
    text = text.replace(/\u2022\s*(Pass|Fail)$/i, '').trim();
    return text.length ? text : 'NA';
  };

  const normalizeRule = (value: string | undefined): string => {
    if (!value) return 'Configured in defaults';
    return value
      .replace(/^Rule\s*:\s*/i, '')
      .replace(/value\s*vs\s*/i, '')
      .replace(/>=/g, '≥')
      .replace(/<=/g, '≤')
      .replace(/\s+/g, ' ')
      .trim();
  };

  const composeComparison = (actual: string, rule: string): string => {
    if (!rule || rule === 'Configured in defaults') {
      return actual;
    }
    const bracket = rule.match(/\[([^\]]+)\]/) || rule.match(/\(([^)]+)\)/);
    if (bracket) {
      const parts = bracket[1]
        .split(',')
        .map((part) => part.trim())
        .filter(Boolean);
      if (parts.length) {
        return `${actual} in ${parts.join(' … ')}`;
      }
    }
    const comparatorPrefix = rule.match(/^(≥|≤|>|<|=)\s*(.+)$/);
    if (comparatorPrefix) {
      return `${actual} ${comparatorPrefix[1]} ${comparatorPrefix[2]}`;
    }
    if (/(≥|≤|>|<|=)/.test(rule)) {
      return `${actual} ${rule}`;
    }
    return `${actual} • ${rule}`;
  };

  const passed = evaluation.pass_count ?? evaluation.checks.filter((c) => c.pass).length;
  const total = evaluation.total_count ?? evaluation.checks.length;
  const selectionMeta = selection ?? null;

  const formatPrice = (value: number | null | undefined): string | null => {
    if (value === null || value === undefined || Number.isNaN(value)) return null;
    return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value);
  };
  const formattedRMultiple =
    selectionMeta?.rMultiple != null ? selectionMeta.rMultiple.toFixed(2) : null;
  const formattedStopPrice = formatPrice(selectionMeta?.stopPrice);
  const formattedTargetPrice = formatPrice(selectionMeta?.targetPrice);
  const selectionDetails: string[] = [];
  if (formattedRMultiple) selectionDetails.push(`R ${formattedRMultiple}`);
  if (formattedStopPrice) selectionDetails.push(`Stop ${formattedStopPrice}`);
  if (formattedTargetPrice) selectionDetails.push(`Target ${formattedTargetPrice}`);

  return (
    <Box sx={{ mt: 2.5, mb: 2 }}>
      <SectionHeader>Buy Checklist</SectionHeader>
      <Box>
        <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
          {`${evaluation.flag ? 'BUY = Yes' : 'BUY = No'} • ${passed} / ${total} passed`}
        </Typography>
        {evaluation.reasons_inline ? (
          <Typography variant="caption" color="text.secondary" sx={{ mt: 0.25 }}>
            {evaluation.reasons_inline}
          </Typography>
        ) : null}
        {evaluation.failed_codes && evaluation.failed_codes.length ? (
          <Typography variant="caption" color="error.main" sx={{ mt: 0.25 }}>
            {`Failed: ${evaluation.failed_codes.join(', ')}`}
          </Typography>
        ) : null}
        {selectionMeta?.selected ? (
          <>
            <Typography variant="caption" color="success.main" sx={{ mt: 0.25, fontWeight: 600 }}>
              {`Selected${selectionMeta.reason ? ` — ${selectionMeta.reason}` : ''}`}
            </Typography>
            {selectionDetails.length ? (
              <Typography variant="caption" color="success.main">
                {selectionDetails.join(' • ')}
              </Typography>
            ) : null}
          </>
        ) : selectionMeta?.reason ? (
          <Typography variant="caption" color="text.secondary" sx={{ mt: 0.25 }}>
            {`Not selected — ${selectionMeta.reason}`}
          </Typography>
        ) : null}
      </Box>
      <Box
        sx={{
          mt: 1.5,
          border: 1,
          borderColor: 'divider',
          borderRadius: 1.5,
          overflow: 'hidden',
        }}
      >
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: 'minmax(140px, 0.9fr) minmax(220px, 1.4fr) auto',
            gap: 1,
            px: 2,
            py: 1,
            bgcolor: 'action.hover',
          }}
        >
          <Typography variant="caption" sx={checklistHeaderCellSx}>
            Factor
          </Typography>
          <Typography variant="caption" sx={checklistHeaderCellSx}>
            Value vs Rule
          </Typography>
          <Typography variant="caption" sx={{ ...checklistHeaderCellSx, textAlign: 'center' }}>
            Pass?
          </Typography>
        </Box>
        {evaluation.checks.map((check, idx) => {
          const actual = sanitizeActual(
            check.actual ?? (check as any).value_display ?? (check as any).value,
          );
          const rule = normalizeRule(
            (check.rule as string | undefined) ??
              (check as any).rule_text ??
              (check as any).value_vs_rule ??
              (check as any).description,
          );
          const comparison = composeComparison(actual, rule);

          return (
            <Box
              key={check.code || `${idx}`}
              sx={{
                display: 'grid',
                gridTemplateColumns: 'minmax(140px, 0.9fr) minmax(220px, 1.4fr) auto',
                gap: 1,
                px: 2,
                py: 1.2,
                borderTop: '1px solid',
                borderColor: 'divider',
              }}
            >
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                {check.label || check.code || `Gate ${idx + 1}`}
              </Typography>
              <Box
                sx={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 0.25,
                  fontVariantNumeric: 'tabular-nums',
                }}
              >
                <Typography
                  variant="body2"
                  color={check.pass ? 'success.main' : 'error.main'}
                  sx={{ fontWeight: 600 }}
                >
                  {comparison}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {rule}
                </Typography>
              </Box>
              <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
                {check.pass ? (
                  <CheckCircleRoundedIcon fontSize="small" color="success" />
                ) : (
                  <CancelRoundedIcon fontSize="small" color="error" />
                )}
              </Box>
            </Box>
          );
        })}
      </Box>
    </Box>
  );
}
export default function RightDrawer({ symbol, open, onClose, runId, asOf }: Props) {
  const sym = symbol || '';
  const enabled = Boolean(open && sym);

  // Build query params for the detail API: prefer intraday run_id, else EOD as_of
  const detailParams = React.useMemo(() => {
    return {
      run_id: runId || undefined,
      as_of: !runId && asOf ? asOf : undefined,
    };
  }, [runId, asOf]);

  // Pass snapshot context to the hook (it supports params as 2nd arg in our app)
  const { data, isFetching, error, refetch: refetchDetail } = useInstrumentDetail(
    sym,
    detailParams as any,
    { enabled, staleTimeMs: 60_000 }
  );

  // Refetch when snapshot context changes (while drawer stays open)
  React.useEffect(() => {
    if (!enabled) return;
    refetchDetail();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, sym, runId, asOf]);

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
  const diagnostics = d?.diagnostics || {};
  const buyEvaluation = React.useMemo<BuyEvaluation | undefined>(() => {
    const direct = diagnostics?.buy_evaluation as BuyEvaluation | undefined;
    if (direct && Array.isArray(direct.checks) && direct.checks.length) {
      return {
        ...direct,
        checks: direct.checks.map((item) => ({
          ...item,
          rule: (item.rule ?? '').toString(),
          actual: (item.actual ?? '').toString(),
        })),
      };
    }

    const legacy = diagnostics?.buy_checklist as DrawerDiagnosticsBuyChecklist | undefined;
    if (!legacy || !Array.isArray(legacy.items) || legacy.items.length === 0) {
      return direct;
    }

    const checks = legacy.items.map((item, idx) => ({
      code: item.code ?? item.factor ?? `gate_${idx + 1}`,
      label: item.factor ?? item.code ?? `Gate ${idx + 1}`,
      rule: (item.description ?? item.value_vs_rule ?? '').toString(),
      actual: (item.value_display ?? item.value_vs_rule ?? '').toString(),
      pass: Boolean(item.passed),
    }));

    return {
      flag: Boolean(legacy.passed),
      profile: legacy.label ?? undefined,
      mode: legacy.mode ?? undefined,
      pass_count: legacy.passed_items ?? checks.filter((c) => c.pass).length,
      total_count: legacy.total_items ?? checks.length,
      checks,
      failed_codes: checks.filter((c) => !c.pass).map((c) => c.code ?? ''),
      enforced_checks: legacy.items
        .map((item) => item.code ?? item.factor ?? '')
        .filter((code) => Boolean(code) && typeof code === 'string'),
      reasons_inline: legacy.summary ?? undefined,
      eval_ts: undefined,
    } as BuyEvaluation;
  }, [diagnostics]);
  const selection = React.useMemo<SelectionMeta>(() => {
    const raw = (d?.selection ?? {}) as Record<string, unknown>;
    const coerceNumber = (value: unknown): number | null => {
      if (typeof value === 'number' && Number.isFinite(value)) return value;
      if (typeof value === 'string') {
        const parsed = Number(value);
        if (Number.isFinite(parsed)) return parsed;
      }
      return null;
    };
    return {
      selected: Boolean(
        raw.selected ??
          (d as any)?.buy_selected ??
          (diagnostics?.buy_evaluation as any)?.selected ??
          false,
      ),
      reason:
        (raw.reason as string | undefined) ??
        (d as any)?.buy_selection_reason ??
        undefined,
      rMultiple:
        coerceNumber(raw.r_multiple) ??
        coerceNumber((d as any)?.buy_r_multiple) ??
        null,
      stopPrice:
        coerceNumber(raw.stop_price) ?? coerceNumber((d as any)?.buy_stop_price) ?? null,
      targetPrice:
        coerceNumber(raw.target_price) ??
        coerceNumber((d as any)?.buy_target_price) ??
        null,
      runId:
        (raw.run_id as string | undefined) ??
        (d as any)?.buy_selection_run_id ??
        undefined,
      tradingDay:
        (raw.trading_day as string | undefined) ??
        (d as any)?.buy_selection_trading_day ??
        undefined,
    };
  }, [d, diagnostics]);
  const alertEvents = d?.alerts?.recent_events;

  const pctToday =
    header?.pct_1d ?? d?.pct_today ?? d?.change_pct_1d ?? d?.change_pct;
  const runIdResolved = d?.run_id ?? d?.resolved_run_id;

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
  const activePosition = tradeOn ? (position ?? posFromDetail ?? null) : null;

  // Tabs state (0 = Overview, 1 = News)
  const [tab, setTab] = React.useState<number>(0);
  const handleTab = (_e: any, v: number) => setTab(v);

  // News hook (enabled only when News tab is active)
  const newsLookbackHours = React.useMemo(() => {
    const raw = Number(d?.news_recent_hours ?? undefined);
    if (Number.isFinite(raw) && raw > 0) return raw;
    return 168;
  }, [d?.news_recent_hours]);

  const newsRangeLabel = React.useMemo(() => {
    if (!Number.isFinite(newsLookbackHours)) return '7 days';
    if (newsLookbackHours % 24 === 0) {
      const days = Math.round(newsLookbackHours / 24);
      return days === 1 ? '24h' : `${days} days`;
    }
    return `${newsLookbackHours}h`;
  }, [newsLookbackHours]);

  const toISO = React.useMemo(() => new Date().toISOString(), [sym, tab]);
  const fromISO = React.useMemo(
    () => new Date(Date.now() - newsLookbackHours * 3600 * 1000).toISOString(),
    [sym, tab, newsLookbackHours]
  );

  const newsParams = React.useMemo(() => {
    if (!sym) return undefined;
    return {
      symbol: sym,
      from: fromISO,
      to: toISO,
      sort: 'impact_desc',
    } as const;
  }, [sym, fromISO, toISO]);

  const {
    data: newsPages,
    isLoading: newsLoading,
    isError: newsError,
    fetchNextPage: fetchMoreNews,
    hasNextPage: hasMoreNews,
    isFetchingNextPage: loadingMoreNews,
    refetch: refetchNews,
  } = useAllNewsInfinite(newsParams, {
    perPage: 200,
    staleTimeMs: 60_000,
    enabled: Boolean(newsParams) && tab === 1,
  });

  const newsItems = React.useMemo(() => {
    if (!newsPages?.pages) return [] as NewsCard[];
    const seen = new Set<string>();
    const out: NewsCard[] = [];
    for (const page of newsPages.pages) {
      for (const it of page.items ?? []) {
        if (!seen.has(it.cluster_id)) {
          seen.add(it.cluster_id);
          out.push(it as NewsCard);
        }
      }
    }
    return out;
  }, [newsPages]);

  React.useEffect(() => {
    if (tab !== 1) return;
    if (newsItems.length > 0) return;
    if (!hasMoreNews || loadingMoreNews) return;
    fetchMoreNews();
  }, [tab, newsItems.length, hasMoreNews, loadingMoreNews, fetchMoreNews]);

  const isInitialNewsLoading = newsLoading || (loadingMoreNews && newsItems.length === 0);

  // ⛳ gate to ignore sync effect while unlocking/refetching
  const unlockingRef = React.useRef(false);

  const lockMut = useLockPosition();
  const unlockMut = useUnlockPosition();
  const [askConfirm, setAskConfirm] = React.useState(false);
  const [sellPriceInput, setSellPriceInput] = React.useState('');
  const [sellPriceError, setSellPriceError] = React.useState<string | null>(null);


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

  React.useEffect(() => {
    if (!askConfirm) return;
    const fallback =
      typeof header?.price === 'number'
        ? header.price
        : typeof d?.price === 'number'
        ? d?.price
        : typeof refs?.entry_suggested === 'number'
        ? refs.entry_suggested
        : typeof roundedEffectiveEntry === 'number'
        ? roundedEffectiveEntry
        : undefined;
    if (typeof fallback === 'number' && Number.isFinite(fallback)) {
      setSellPriceInput(fallback.toFixed(2));
    } else {
      setSellPriceInput('');
    }
    setSellPriceError(null);
  }, [askConfirm, header?.price, d?.price, refs?.entry_suggested, roundedEffectiveEntry]);

  const breakeven_active =
    String(ab?.breakeven_state || '').toUpperCase() === 'ACTIVE';
  const euphoria_on = String(ab?.euphoria_state || '').toUpperCase() === 'ON';

  const formatDecimal = React.useCallback((value: number | null | undefined) => {
    if (typeof value !== 'number' || !Number.isFinite(value)) return '--';
    return value.toFixed(2);
  }, []);

  const alertTemplates = Array.isArray(d?.alert_templates) ? (d.alert_templates as AlertTemplate[]) : undefined;

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

    const parsed = Number.parseFloat(sellPriceInput || '');
    if (!Number.isFinite(parsed) || parsed <= 0) {
      setSellPriceError('Enter a valid sell price');
      return;
    }

    const sellPrice = Number(parsed.toFixed(2));
    const payload = {
      trade_on: false,
      sell_price: sellPrice,
      sold_at: new Date().toISOString(),
    } as const;

    unlockingRef.current = true;
    setSellPriceError(null);

    try {
      await unlockMut.mutateAsync({ id, data: payload });
      setAskConfirm(false);
      setTradeOn(false);
      setEntryPrice(computeSuggestedPriceStr());
      setQtyLocal('');
      setSellPriceInput('');
      await Promise.all([refetchPosition(), refetchDetail()]);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to close trade';
      setSellPriceError(message);
    } finally {
      unlockingRef.current = false;
    }
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
          name={header?.name ?? d?.name ?? symbol ?? '--'}
          sector={header?.sector ?? d?.sector}
          price={header?.price ?? d?.price}
          pctToday={pctToday}
          runId={runIdResolved}
          badges={badges}
          onClose={onClose}
        />

        <Tabs value={tab} onChange={handleTab} variant="fullWidth" sx={{ mt: 0.5 }}>
          <Tab label="Overview" />
          <Tab label="News" />
        </Tabs>
      </Box>

      {/* BODY */}
      <Box sx={{ px: 3, py: 2, overflowY: 'auto' }}>
        {/* OVERVIEW tab */}
        {tab === 0 && (
          <React.Fragment>
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

            <BuyChecklistSection evaluation={buyEvaluation} />

            {tradeOn && activePosition ? (
              <React.Fragment>
                <SectionHeader>Active Position</SectionHeader>
                <Box
                  sx={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
                    gap: 1.5,
                    mb: 1.5,
                  }}
                >
                  <Box>
                    <Typography variant="caption" color="text.secondary">
                      Entry Price
                    </Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                      {formatDecimal(activePosition?.entry_price_locked)}
                    </Typography>
                  </Box>
                  <Box>
                    <Typography variant="caption" color="text.secondary">
                      Quantity
                    </Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                      {typeof activePosition?.qty === 'number' ? activePosition.qty : '--'}
                    </Typography>
                  </Box>
                  <Box>
                    <Typography variant="caption" color="text.secondary">
                      Stop
                    </Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                      {formatDecimal(activePosition?.stop_now)}
                    </Typography>
                  </Box>
                  <Box>
                    <Typography variant="caption" color="text.secondary">
                      Note
                    </Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600, wordBreak: 'break-word' }}>
                      {activePosition?.note ? activePosition.note : '--'}
                    </Typography>
                  </Box>
                </Box>
              </React.Fragment>
            ) : null}

            <EntryModule
              effectiveEntry={
                typeof roundedEffectiveEntry === 'number' ? roundedEffectiveEntry : undefined
              }
              locked={locked}
              trade_on={tradeOn}
              qty={qtyServer ?? undefined}
              onTradeChange={(on) => {
                if (on) {
                  setTradeOn(true);
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
              showLockEntryButton={false}
            />

            {tradeOn && !locked && (
              <Box sx={{ display: 'flex', gap: 1, mt: 1 }}>
                <Button variant="contained" onClick={lockNow}>
                  Lock trade
                </Button>
                <Button
                  variant="outlined"
                  onClick={() => {
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
            <AlertsRow templates={alertTemplates} events={alertEvents} />

            <Box sx={{ color: 'text.secondary', fontSize: 12, mt: 2, pb: 1 }}>
              {d?.as_of || header?.as_of ? `As of ${new Date(d?.as_of ?? header?.as_of).toLocaleString()}` : ''}
              {isFetching ? ' · refreshing…' : ''}
              {d?.trading_day ? ` · ${d.trading_day}` : ''}
              {runIdResolved ? ` · Run ${runIdResolved}` : ''}
              {d?.symbol_canon ? ` · ${d.symbol_canon}` : ''}
              {error ? ` · ${(error as any)?.message || 'Failed to load details.'}` : ''}
            </Box>
          </React.Fragment>
        )}

        {/* NEWS tab */}
        {tab === 1 && (
          <React.Fragment>
            {isInitialNewsLoading ? (
              <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
                <CircularProgress size={22} />
              </Box>
            ) : newsError ? (
              <Typography variant="body2" color="error">
                Failed to load news.
              </Typography>
            ) : !newsItems.length ? (
              <Typography variant="body2" color="text.secondary">
                No news in the last {newsRangeLabel}.
              </Typography>
            ) : (
              <React.Fragment>
                <List disablePadding>
                  {newsItems.map((it, idx) => {
                    const title = it.title;
                    const srcText = it.source_primary || it.sources?.[0]?.publisher || '';
                    const href = it.source_url || it.sources?.[0]?.url || '';
                    const bullets = (it.bullets || []).slice(0, 3).map((b) => b.replace(/^•\s?/, ''));

                    return (
                      <React.Fragment key={it.cluster_id || `${idx}`}>
                        <ListItem alignItems="flex-start" disableGutters sx={{ py: 1.25 }}>
                          <ListItemText
                            primary={
                              <Typography variant="subtitle2" sx={{ lineHeight: 1.3 }}>
                                {title}
                              </Typography>
                            }
                            secondary={
                              <Box sx={{ mt: 0.5 }}>
                                {bullets.length ? (
                                  <ul style={{ margin: 0, paddingLeft: '1.1rem' }}>
                                    {bullets.map((b, i) => (
                                      <li key={i}>
                                        <Typography variant="body2">{b}</Typography>
                                      </li>
                                    ))}
                                  </ul>
                                ) : null}
                                {it.why ? (
                                  <Typography
                                    variant="caption"
                                    color="text.secondary"
                                    display="block"
                                    sx={{ mt: 0.5 }}
                                  >
                                    {it.why}
                                  </Typography>
                                ) : null}
                                {href ? (
                                  <Typography variant="caption" display="block" sx={{ mt: 0.75 }}>
                                    Source:{' '}
                                    <Link href={href} target="_blank" rel="noopener noreferrer" underline="hover">
                                      {srcText || 'link'}
                                    </Link>
                                  </Typography>
                                ) : srcText ? (
                                  <Typography
                                    variant="caption"
                                    color="text.secondary"
                                    display="block"
                                    sx={{ mt: 0.75 }}
                                  >
                                    Source: {srcText}
                                  </Typography>
                                ) : null}
                              </Box>
                            }
                          />
                        </ListItem>
                        {idx < newsItems.length - 1 ? <Divider component="li" /> : null}
                      </React.Fragment>
                    );
                  })}
                </List>
                {loadingMoreNews ? (
                  <Box sx={{ display: 'flex', justifyContent: 'center', py: 2 }}>
                    <CircularProgress size={18} />
                  </Box>
                ) : hasMoreNews ? (
                  <Box sx={{ display: 'flex', justifyContent: 'center', mt: 1 }}>
                    <Button onClick={() => fetchMoreNews()} size="small" variant="outlined">
                      Load more
                    </Button>
                  </Box>
                ) : null}
              </React.Fragment>
            )}
          </React.Fragment>
        )}
      </Box>

      {/* Unlock confirmation */}
      <Dialog
        open={askConfirm}
        onClose={() => {
          setAskConfirm(false);
          setSellPriceError(null);
        }}
      >
        <DialogTitle>Close trade?</DialogTitle>
        <DialogContent sx={{ pt: 2 }}>
          <Typography variant="body2" sx={{ mb: 2 }}>
            Enter the sell price to mark {sym} as closed and capture realized P/L.
          </Typography>
          <TextField
            autoFocus
            fullWidth
            label="Sell price"
            type="number"
            value={sellPriceInput}
            onChange={(event) => {
              setSellPriceInput(event.target.value);
              if (sellPriceError) setSellPriceError(null);
            }}
            inputProps={{ min: 0, step: '0.01' }}
            error={Boolean(sellPriceError)}
            helperText={sellPriceError || 'Example: 512.35'}
          />
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => {
              setAskConfirm(false);
              setSellPriceError(null);
            }}
            disabled={unlockMut.isPending}
          >
            Cancel
          </Button>
          <Button
            onClick={unlockNow}
            variant="contained"
            color="error"
            disabled={unlockMut.isPending}
          >
            Close trade
          </Button>
        </DialogActions>
      </Dialog>
    </Drawer>
  );
}
