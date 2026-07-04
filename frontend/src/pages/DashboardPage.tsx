// src/pages/Dashboard.tsx
import * as React from 'react';
import { useOutletContext } from 'react-router-dom';
import type { OutletCtx } from '../layouts/AppShell';
import {
  Box,
  CircularProgress,
  Divider,
  Grid,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  ToggleButton,
  ToggleButtonGroup,
  Chip,
  Typography,
  TextField,
  Button,
} from '@mui/material';
import dayjs from 'dayjs';
import { useQueries } from '@tanstack/react-query';
import SparklineRe, { SparklineRange } from '@/features/detail/SparklineRe';
import {
  getGetApiV1InstrumentsSymbolDetailQueryOptions,
  useGetApiV1Positions,
  useGetTopMovers,
  useGetCandidatePool,
} from '@/lib/api/client';
import axios from 'axios';
import { TopMoversPeriod } from '@/lib/api/types';
import type {
  DrawerSparkline,
  DrawerDetail,
  TopMoverEntry,
  TopMoversPeriod as TopMoversPeriodValue,
  PositionOut,
  CandidatePoolList,
} from '@/lib/api/types';
import RightDrawer from '@/features/detail/RightDrawer';
import SectorHeatmap from '../components/SectorHeatmap';
import { displaySymbol, displayDate, displayDateTime } from '@/lib/formatters';
import InfoTooltip from '@/components/InfoTooltip';

const PERIOD_OPTIONS: { label: string; value: TopMoversPeriodValue }[] = [
  { label: '1 Day', value: TopMoversPeriod['1d'] },
  { label: '1 Week', value: TopMoversPeriod['1w'] },
  { label: '1 Month', value: TopMoversPeriod['1m'] },
  { label: '3 Months', value: TopMoversPeriod['3m'] },
];

const currencyFormatter = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 2,
});

const percentFormatter = new Intl.NumberFormat('en-US', {
  maximumFractionDigits: 2,
  signDisplay: 'exceptZero',
});

const formatPrice = (value?: number | null) => (value == null ? '—' : currencyFormatter.format(value));
const formatPercent = (value?: number | null) => (value == null ? '—' : `${percentFormatter.format(value)}%`);
const formatScore = (value?: number | null) => (value == null ? '—' : value.toFixed(0));
const formatNumber = (value?: number | null, decimals = 1) => (value == null ? '—' : value.toFixed(decimals));
const changeColor = (value?: number | null) => (value == null ? 'inherit' : value > 0 ? 'success.main' : value < 0 ? 'error.main' : 'text.secondary');
const poolStatusMeta: Record<string, { label: string; color: 'default' | 'success' | 'warning' | 'error' }> = {
  strong: { label: 'Strong', color: 'success' },
  weakening: { label: 'Weakening', color: 'warning' },
  exit_soon: { label: 'Exit soon', color: 'error' },
  removed: { label: 'Removed', color: 'default' },
};
const formatDateLabel = (value?: string | null) => displayDate(value);
const formatPercentCompact = (value?: number | null) => {
  if (value == null) return '—';
  return `${percentFormatter.format(value)}%`;
};

const rangeSinceTrade = (_createdAt?: string) => '';

interface MoversTableProps {
  title: string;
  rows: TopMoverEntry[];
  onSelect?: (symbol: string) => void;
}

const MoversTable: React.FC<MoversTableProps> = ({ title, rows, onSelect }) => (
  <Stack spacing={1} sx={{ height: '100%' }}>
    <Typography variant="subtitle2">{title}</Typography>
    <Table size="small">
      <TableHead>
        <TableRow>
          <TableCell>Ticker</TableCell>
          <TableCell align="right">Price</TableCell>
          <TableCell align="right">Change</TableCell>
          <TableCell align="right">Score</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {rows.length === 0 ? (
          <TableRow>
            <TableCell colSpan={4} align="center" sx={{ color: 'text.secondary' }}>
              No data available
            </TableCell>
          </TableRow>
        ) : (
          rows.map((row) => (
            <TableRow
              key={row.symbol}
              hover
              sx={{ cursor: onSelect ? 'pointer' : 'default' }}
              onClick={() => onSelect?.(row.symbol)}
            >
              <TableCell>
                <Typography variant="body2" fontWeight={600}>
                  {displaySymbol(row.symbol)}
                </Typography>
                {row.name ? (
                  <Typography variant="caption" color="text.secondary">
                    {row.name}
                  </Typography>
                ) : null}
              </TableCell>
              <TableCell align="right">{formatPrice(row.price)}</TableCell>
              <TableCell align="right" sx={{ color: changeColor(row.change_pct) }}>
                {formatPercent(row.change_pct)}
              </TableCell>
              <TableCell align="right">{formatScore(row.score)}</TableCell>
            </TableRow>
          ))
        )}
      </TableBody>
    </Table>
  </Stack>
);

export default function Dashboard() {
  const { refetchIntervalMs } = useOutletContext<OutletCtx>();
  const [period, setPeriod] = React.useState<TopMoversPeriodValue>(TopMoversPeriod['1d']);
  const [drawerSymbol, setDrawerSymbol] = React.useState<string | null>(null);
  const [drawerAsOf, setDrawerAsOf] = React.useState<string | undefined>(undefined);
  const [drawerOpen, setDrawerOpen] = React.useState(false);

  const moversQuery = useGetTopMovers(
    { period },
    {
      axios: { baseURL: '' },
      query: {
        keepPreviousData: true,
        refetchInterval: refetchIntervalMs || false,
        retry: 0,
        refetchOnWindowFocus: false,
        refetchOnReconnect: false,
      },
    }
  );

  const moversData = moversQuery.data?.data;

  const candidatePoolQuery = useGetCandidatePool(undefined, {
    axios: { baseURL: '' },
    query: {
      refetchInterval: refetchIntervalMs || false,
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
      retry: 0,
    },
  });
  const candidatePool = (candidatePoolQuery.data?.data as CandidatePoolList | undefined) ?? undefined;
  const [poolDate, setPoolDate] = React.useState<string>('');
  const [poolOverride, setPoolOverride] = React.useState<CandidatePoolList | null>(null);
  const [poolOverrideLoading, setPoolOverrideLoading] = React.useState(false);
  const [poolOverrideError, setPoolOverrideError] = React.useState<string | null>(null);

  const handleLoadPoolDate = React.useCallback(async () => {
    if (!poolDate) {
      setPoolOverride(null);
      setPoolOverrideError(null);
      return;
    }
    setPoolOverrideLoading(true);
    setPoolOverrideError(null);
    try {
      const resp = await axios.get('/api/v1/candidate-pool/history', { params: { date: poolDate } });
      setPoolOverride(resp.data as CandidatePoolList);
    } catch (err: any) {
      setPoolOverrideError(err?.response?.data?.detail || 'Failed to load pool history');
      setPoolOverride(null);
    } finally {
      setPoolOverrideLoading(false);
    }
  }, [poolDate]);

  const poolData = poolOverride ?? candidatePool;
  const poolLoading = poolOverride ? poolOverrideLoading : candidatePoolQuery.isLoading;
  const poolError = poolOverrideError || (candidatePoolQuery.isError ? 'Unable to load candidate pool right now.' : null);
  const poolItems = React.useMemo(
    () => (poolData?.items ? [...poolData.items].sort((a, b) => (a.rank ?? 0) - (b.rank ?? 0)) : []),
    [poolData]
  );

  const handlePeriodChange = (_event: React.SyntheticEvent<Element, Event>, value: TopMoversPeriodValue | null) => {
    if (value) {
      setPeriod(value);
    }
  };

  const handleOpenDrawer = React.useCallback(
    (symbol: string, asOfHint?: string | null) => {
      setDrawerSymbol(symbol);
      setDrawerAsOf(asOfHint ?? poolData?.as_of ?? undefined);
      setDrawerOpen(true);
    },
    [poolData]
  );

  const handleCloseDrawer = React.useCallback(() => {
    setDrawerOpen(false);
    setDrawerSymbol(null);
    setDrawerAsOf(undefined);
  }, []);

  const positionsQuery = useGetApiV1Positions(undefined, {
    axios: { baseURL: '' },
    query: {
      refetchInterval: refetchIntervalMs || false,
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
    },
  });

  const positions = (positionsQuery.data?.data as PositionOut[] | undefined) ?? [];
  const activeTrades = React.useMemo(() => positions.filter((p) => p.trade_on), [positions]);
  const [sparklineRanges, setSparklineRanges] = React.useState<Record<string, SparklineRange>>({});
  const rangeFor = React.useCallback(
    (symbol: string) => sparklineRanges[symbol] ?? '30d',
    [sparklineRanges]
  );

  const detailQueries = useQueries({
    queries: activeTrades.map((p) =>
      getGetApiV1InstrumentsSymbolDetailQueryOptions(
        p.symbol,
        { sparkline_window: rangeFor(p.symbol) } as any,
        {
          axios: { baseURL: '' },
          query: {
            enabled: !!p.symbol,
            refetchInterval: refetchIntervalMs || false,
            refetchOnWindowFocus: false,
            refetchOnReconnect: false,
            select: (res) => res.data as DrawerDetail,
          },
        }
      )
    ),
  });

  const detailBySymbol = React.useMemo(() => {
    const map = new Map<string, DrawerDetail | undefined>();
    detailQueries.forEach((q, idx) => {
      const sym = activeTrades[idx]?.symbol;
      if (sym) map.set(sym, q.data as DrawerDetail | undefined);
    });
    return map;
  }, [detailQueries, activeTrades]);

  return (
    <Stack spacing={3}>
      <SectorHeatmap refetchIntervalMs={refetchIntervalMs} />

      <Paper sx={{ p: 2, width: '100%' }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1, flexWrap: 'wrap', gap: 1 }}>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ flexWrap: 'wrap', rowGap: 0.5 }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 800, letterSpacing: '.02em' }}>
              Active Buy Candidates (Pool)
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {poolData
                ? `Max ${poolData.max_size} · Updated ${
                    poolData.generated_at
                      ? displayDateTime(poolData.generated_at as string)
                      : poolData.as_of ?? 'latest'
                  }`
                : 'Relaxed intraday rules apply only to these symbols'}
            </Typography>
          </Stack>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ flexWrap: 'wrap', rowGap: 0.5 }}>
            <TextField
              label="Pool as of date"
              type="date"
              size="small"
              value={poolDate}
              onChange={(e) => setPoolDate(e.target.value)}
              InputLabelProps={{ shrink: true }}
            />
            <Button variant="outlined" size="small" onClick={handleLoadPoolDate} disabled={poolOverrideLoading}>
              {poolDate ? 'Load date' : 'Latest'}
            </Button>
            {poolOverride ? (
              <Button variant="text" size="small" onClick={() => { setPoolDate(''); setPoolOverride(null); setPoolOverrideError(null); }}>
                Clear
              </Button>
            ) : null}
          </Stack>
        </Stack>
        <Divider sx={{ mb: 1.5 }} />
        {poolError ? (
          <Typography color="error">{poolError}</Typography>
        ) : poolLoading && poolItems.length === 0 ? (
          <Stack alignItems="center" justifyContent="center" sx={{ py: 4 }}>
            <CircularProgress size={24} />
          </Stack>
        ) : poolItems.length === 0 ? (
          <Typography color="text.secondary" sx={{ py: 2 }}>
            Pool is empty. EOD buy candidates will accumulate here until relaxed exits trigger.
          </Typography>
        ) : (
          <Table size="small" sx={{ '& td, & th': { whiteSpace: 'nowrap' } }}>
            <TableHead>
              <TableRow>
                <TableCell>Rank</TableCell>
                <TableCell>Symbol</TableCell>
                <TableCell>Added</TableCell>
                <TableCell align="right">Score</TableCell>
                <TableCell align="right">ADX</TableCell>
                <TableCell align="right">
                  <Stack direction="row" spacing={0.5} alignItems="center" justifyContent="flex-end">
                    <span>R</span>
                    <InfoTooltip
                      title="Reward-to-risk (R)"
                      body="Uses current price, an ATR-based stop, and the T1 target sale price to estimate potential reward per unit of risk. Higher R means a better cushion between stop and target profit like 10%."
                    />
                  </Stack>
                </TableCell>
                <TableCell align="right">52W</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Notes</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {poolItems.map((item) => {
                const statusMeta = poolStatusMeta[item.status] || poolStatusMeta.strong;
                const reasons = item.reasons?.filter(Boolean) ?? [];
                return (
                  <TableRow
                  hover
                  key={item.symbol}
                  sx={{ cursor: 'pointer' }}
                  onClick={() => handleOpenDrawer(item.symbol)}
                >
                    <TableCell>
                      <Stack direction="row" alignItems="center" spacing={1}>
                        <Typography fontWeight={700}>#{item.rank ?? '—'}</Typography>
                        {item.is_top_candidate ? <Chip size="small" color="warning" label="Top pick" /> : null}
                      </Stack>
                    </TableCell>
                  <TableCell>
                    <Typography variant="body2" fontWeight={700}>
                      {displaySymbol(item.symbol)}
                    </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {item.added_as_of ? `EOD ${displayDate(item.added_as_of)}` : ''}
                      </Typography>
                    </TableCell>
                    <TableCell>{formatDateLabel(item.added_on)}</TableCell>
                    <TableCell align="right">{formatScore(item.score)}</TableCell>
                    <TableCell align="right">{formatNumber(item.adx14, 0)}</TableCell>
                    <TableCell align="right">{formatNumber(item.r_multiple, 2)}</TableCell>
                    <TableCell align="right">{formatPercentCompact(item.prox_52w_high_pct)}</TableCell>
                    <TableCell>
                      <Chip size="small" color={statusMeta.color} label={statusMeta.label} variant={item.status === 'strong' ? 'filled' : 'outlined'} />
                    </TableCell>
                    <TableCell>
                      <Stack direction="row" spacing={0.5} flexWrap="wrap">
                        {(reasons.length ? reasons : ['Relaxed exit rules intact']).map((r, idx) => (
                          <Chip key={idx} size="small" variant="outlined" color="info" label={r} />
                        ))}
                        {item.exit_checks?.map((check) => {
                          const label =
                            check.code === 'age' && typeof check.value === 'number'
                              ? `Age: ${Math.round(check.value)}d`
                              : check.label;
                          return (
                            <Chip
                              key={check.code}
                              size="small"
                              variant={check.pass ? 'outlined' : 'filled'}
                              color={check.pass ? 'success' : 'error'}
                              label={label}
                            />
                          );
                        })}
                      </Stack>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
        <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
          Relaxed intraday checks apply only to pool members; ranking blends score, R-multiple, ADX, and 52W proximity.
        </Typography>
      </Paper>

      <Paper sx={{ p: 2, width: '100%' }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1, flexWrap: 'wrap', gap: 1 }}>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ flexWrap: 'wrap', rowGap: 0.5 }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 800, letterSpacing: '.02em' }}>
              Top Movers
            </Typography>
            {moversData ? (
              <Typography variant="caption" color="text.secondary">
                {`Snapshot ${displayDate(moversData.as_of ?? 'latest')} • Updated ${displayDateTime(moversData.generated_at)}`}
              </Typography>
            ) : (
              <Typography variant="caption" color="text.secondary">
                Snapshot pending
              </Typography>
            )}
          </Stack>
          <ToggleButtonGroup exclusive value={period} onChange={handlePeriodChange} size="small">
            {PERIOD_OPTIONS.map((option) => (
              <ToggleButton key={option.value} value={option.value} sx={{ textTransform: 'none' }}>
                {option.label}
              </ToggleButton>
            ))}
          </ToggleButtonGroup>
        </Stack>
        <Divider sx={{ mb: 2 }} />
        {moversQuery.isError ? (
          <Typography color="error">Unable to load top movers right now.</Typography>
        ) : moversQuery.isLoading && !moversData ? (
          <Stack alignItems="center" justifyContent="center" sx={{ py: 4 }}>
            <CircularProgress size={24} />
          </Stack>
        ) : (
          <Grid container spacing={2}>
            <Grid item xs={12} md={6}>
              <MoversTable
                title="Top Gainers"
                rows={moversData?.gainers ?? []}
                onSelect={(sym) => handleOpenDrawer(sym, moversData?.as_of)}
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <MoversTable
                title="Top Losers"
                rows={moversData?.losers ?? []}
                onSelect={(sym) => handleOpenDrawer(sym, moversData?.as_of)}
              />
            </Grid>
          </Grid>
        )}
      </Paper>

      <Paper sx={{ p: 2, width: '100%' }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1, gap: 1, flexWrap: 'wrap' }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 800, letterSpacing: '.02em' }}>
            Active Trades
          </Typography>
          <Typography variant="caption" color="text.secondary">
            Price evolution from trade start; updates with live feed
          </Typography>
        </Stack>
        <Divider sx={{ mb: 1 }} />
        {positionsQuery.isError ? (
          <Typography color="error">Unable to load active trades right now.</Typography>
        ) : positionsQuery.isLoading ? (
          <Stack alignItems="center" justifyContent="center" sx={{ py: 4 }}>
            <CircularProgress size={24} />
          </Stack>
        ) : activeTrades.length === 0 ? (
          <Typography color="text.secondary" sx={{ py: 2 }}>
            No active trades to display.
          </Typography>
        ) : (
          <Grid container spacing={2}>
            {activeTrades.map((p, idx) => {
              const detail = detailBySymbol.get(p.symbol);
                const sparkData = detail?.sparkline as DrawerSparkline | undefined;
                const detailQuery = detailQueries[idx];
                const rangeLabel = rangeSinceTrade(p.created_at);
              const ltp =
                typeof detail?.header?.price === 'number'
                  ? detail.header.price
                  : typeof detail?.price === 'number'
                  ? detail.price
                  : Array.isArray(sparkData?.prices_30d) && sparkData!.prices_30d.length > 0
                  ? Number(sparkData!.prices_30d[sparkData!.prices_30d.length - 1])
                  : undefined;

              const qty = typeof p.qty === 'number' ? p.qty : undefined;
              const entry = typeof p.entry_price_locked === 'number' ? p.entry_price_locked : undefined;
              const invested = qty && entry ? qty * entry : undefined;
              const current = qty && typeof ltp === 'number' ? qty * ltp : undefined;
              const pl = current != null && invested != null ? current - invested : undefined;
              const plPct =
                invested && invested > 0 && typeof current === 'number' ? ((current / invested - 1) * 100) : undefined;
              const plColor =
                typeof pl === 'number' ? (pl > 0 ? 'success.main' : pl < 0 ? 'error.main' : 'text.secondary') : 'text.secondary';
              const startedOn = dayjs(p.created_at).isValid()
                ? displayDateTime(p.created_at)
                : 'Unknown';
              return (
                <Grid item xs={12} md={6} lg={4} key={p.id}>
                  <Paper variant="outlined" sx={{ p: 1.5, height: '100%' }}>
                    <Stack direction="row" alignItems="baseline" justifyContent="space-between" sx={{ mb: 1 }}>
                      <Box
                        sx={{ cursor: 'pointer' }}
                        onClick={() => handleOpenDrawer(p.symbol, detail?.as_of ?? poolData?.as_of)}
                      >
                        <Stack direction="row" spacing={1} alignItems="baseline" flexWrap="wrap">
                          <Typography variant="subtitle1" fontWeight={700}>
                            {displaySymbol(p.symbol)}
                          </Typography>
                          <Typography variant="caption" color="text.secondary">
                            Qty: {p.qty ?? '--'} | Entry: {formatPrice(p.entry_price_locked)}
                          </Typography>
                        </Stack>
                      </Box>
                      <Typography variant="caption" color="text.secondary">
                        {rangeLabel}
                      </Typography>
                    </Stack>
                    <Box sx={{ cursor: 'pointer' }} onClick={() => handleOpenDrawer(p.symbol, detail?.as_of ?? poolData?.as_of)}>
                      <SparklineRe
                        data={sparkData as any}
                        height={180}
                        showHeader={false}
                        range={rangeFor(p.symbol)}
                        onRangeChange={(next) =>
                          setSparklineRanges((prev) => ({ ...prev, [p.symbol]: next }))
                        }
                      />
                    </Box>
                    <Stack direction="row" spacing={2} sx={{ mt: 0.5, mb: 0.5, flexWrap: 'wrap' }}>
                      <Stack spacing={0} minWidth={120}>
                        <Typography variant="caption" color="text.secondary">
                          Invested
                        </Typography>
                        <Typography variant="body2">{formatPrice(invested)}</Typography>
                      </Stack>
                      <Stack spacing={0} minWidth={120}>
                        <Typography variant="caption" color="text.secondary">
                          Current
                        </Typography>
                        <Typography variant="body2">{formatPrice(current)}</Typography>
                      </Stack>
                      <Stack spacing={0} minWidth={120}>
                        <Typography variant="caption" color="text.secondary">
                          P/L
                        </Typography>
                        <Typography variant="body2" sx={{ color: plColor, fontWeight: 700 }}>
                          {formatPrice(pl)} {plPct != null ? `(${percentFormatter.format(plPct)}%)` : ''}
                        </Typography>
                      </Stack>
                    </Stack>
                    <Stack direction="row" justifyContent="space-between" alignItems="center">
                      <Typography variant="caption" color="text.secondary">
                        Started: {startedOn}
                      </Typography>
                      {detailQuery?.isLoading || detailQuery?.isFetching ? (
                        <Stack direction="row" alignItems="center" spacing={0.5}>
                          <CircularProgress size={12} />
                          <Typography variant="caption" color="text.secondary">
                            Updating
                          </Typography>
                        </Stack>
                      ) : null}
                    </Stack>
                  </Paper>
                </Grid>
              );
            })}
          </Grid>
        )}
      </Paper>

      <RightDrawer symbol={drawerSymbol} open={drawerOpen} onClose={handleCloseDrawer} asOf={drawerAsOf} />
    </Stack>
  );
}
