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
import { useGetTopMovers } from '@/lib/api/client';
import { TopMoversPeriod } from '@/lib/api/types';
import type { TopMoverEntry, TopMoversPeriod as TopMoversPeriodValue } from '@/lib/api/types';
import MomentumTable from '../components/MomentumTable';
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
          <TableCell>Next Action</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {rows.length === 0 ? (
          <TableRow>
            <TableCell colSpan={5} align="center" sx={{ color: 'text.secondary' }}>
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
              <TableCell>
                <Typography variant="body2" fontWeight={500}>
                  {row.next_action.text}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {row.next_action.code}
                </Typography>
              </TableCell>
            </TableRow>
          ))
        )}
      </TableBody>
    </Table>
  </Stack>
);

export default function Dashboard() {
  const { refetchIntervalMs } = useOutletContext<OutletCtx>();
  const [, setSymbol] = React.useState<string | null>(null);
  const [, setDrawerOpen] = React.useState(false);
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
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
          <Typography variant="subtitle2">Screener</Typography>
          <Typography variant="caption" color="text.secondary">
            Sorted by score (desc)
          </Typography>
        </Stack>
        <Divider sx={{ mb: 1 }} />
        <Box sx={{ width: '100%', overflowX: 'auto' }}>
          <MomentumTable
            onSelectSymbol={(s) => {
              setSymbol(s);
              setDrawerOpen(true);
            }}
            refetchIntervalMs={refetchIntervalMs}
          />
        </Box>
      </Paper>
    </Stack>
  );
}
