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
  Typography,
} from '@mui/material';
import dayjs from 'dayjs';
import { useQueries } from '@tanstack/react-query';
import SparklineRe from '@/features/detail/SparklineRe';
import {
  getGetApiV1InstrumentsSymbolDetailQueryOptions,
  useGetApiV1Positions,
  useGetTopMovers,
} from '@/lib/api/client';
import { TopMoversPeriod } from '@/lib/api/types';
import type {
  DrawerSparkline,
  DrawerDetail,
  TopMoverEntry,
  TopMoversPeriod as TopMoversPeriodValue,
  PositionOut,
} from '@/lib/api/types';
import SectorHeatmap from '../components/SectorHeatmap';

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
const changeColor = (value?: number | null) => (value == null ? 'inherit' : value > 0 ? 'success.main' : value < 0 ? 'error.main' : 'text.secondary');

const rangeSinceTrade = (createdAt?: string) => {
  // Bucket to API-friendly ranges instead of arbitrary days to ensure data returns.
  if (!createdAt) return '90d';
  const start = dayjs(createdAt);
  if (!start.isValid()) return '90d';
  const days = Math.max(1, Math.ceil(dayjs().diff(start, 'day', true)));
  if (days <= 30) return '30d';
  if (days <= 90) return '90d';
  return '1y';
};

interface MoversTableProps {
  title: string;
  rows: TopMoverEntry[];
}

const MoversTable: React.FC<MoversTableProps> = ({ title, rows }) => (
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
            <TableRow key={row.symbol}>
              <TableCell>
                <Typography variant="body2" fontWeight={600}>
                  {row.symbol}
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

  const handlePeriodChange = (_event: React.SyntheticEvent<Element, Event>, value: TopMoversPeriodValue | null) => {
    if (value) {
      setPeriod(value);
    }
  };

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

  const detailQueries = useQueries({
    queries: activeTrades.map((p) =>
      getGetApiV1InstrumentsSymbolDetailQueryOptions(p.symbol, undefined, {
        axios: { baseURL: '' },
        query: {
          enabled: !!p.symbol,
          refetchInterval: refetchIntervalMs || false,
          refetchOnWindowFocus: false,
          refetchOnReconnect: false,
          select: (res) => res.data as DrawerDetail,
        },
      })
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
          <Typography variant="subtitle2">Top Movers</Typography>
          <ToggleButtonGroup exclusive value={period} onChange={handlePeriodChange} size="small">
            {PERIOD_OPTIONS.map((option) => (
              <ToggleButton key={option.value} value={option.value} sx={{ textTransform: 'none' }}>
                {option.label}
              </ToggleButton>
            ))}
          </ToggleButtonGroup>
        </Stack>
        <Typography variant="caption" color="text.secondary" sx={{ mb: 1, display: 'block' }}>
          {moversData
            ? `Snapshot ${moversData.as_of ?? 'latest'} • Updated ${dayjs(moversData.generated_at).format('HH:mm:ss')}`
            : 'Snapshot pending'}
        </Typography>
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
              <MoversTable title="Top Gainers" rows={moversData?.gainers ?? []} />
            </Grid>
            <Grid item xs={12} md={6}>
              <MoversTable title="Top Losers" rows={moversData?.losers ?? []} />
            </Grid>
          </Grid>
        )}
      </Paper>

      <Paper sx={{ p: 2, width: '100%' }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1, gap: 1, flexWrap: 'wrap' }}>
          <Typography variant="subtitle2">Active Trades (since entry)</Typography>
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
                ? dayjs(p.created_at).format('DD/MM/YYYY HH:mm')
                : 'Unknown';
              return (
                <Grid item xs={12} md={6} lg={4} key={p.id}>
                  <Paper variant="outlined" sx={{ p: 1.5, height: '100%' }}>
                    <Stack direction="row" alignItems="baseline" justifyContent="space-between" sx={{ mb: 1 }}>
                      <Box>
                        <Typography variant="subtitle1" fontWeight={700}>
                          {p.symbol}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          Qty: {p.qty ?? '--'} | Entry: {formatPrice(p.entry_price_locked)}
                        </Typography>
                      </Box>
                      <Typography variant="caption" color="text.secondary">
                        Range: {rangeLabel}
                      </Typography>
                    </Stack>
                    <SparklineRe data={sparkData as any} height={180} showHeader={false} />
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
    </Stack>
  );
}
