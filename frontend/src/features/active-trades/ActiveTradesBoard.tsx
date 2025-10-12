import * as React from 'react';
import {
  Box,
  Paper,
  Typography,
  Table,
  TableHead,
  TableRow,
  TableCell,
  TableBody,
  Chip,
  IconButton,
  Tooltip,
  CircularProgress,
  Stack,
  Button,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import { useQuery, useQueries, useQueryClient } from '@tanstack/react-query';

/** --- Types from our backend contracts (lightweight) --- */
type PositionOut = {
  id: number;
  symbol: string;
  entry_price_locked: number | null;
  qty: number | null;
  trade_on: boolean;
  // optional extras
  stop_now?: number | null;
  exit_close_threshold?: number | null;
  created_at?: string;
  updated_at?: string;
  note?: string | null;
  sell_price?: number | null;
  sold_at?: string | null;
  realized_pl?: number | null;
  realized_pl_pct?: number | null;
};

type DrawerDetail = {
  header?: { price?: number; name?: string };
  score_breakdown?: { score_total_0_100?: number };
  score?: number;
  next_action?: { text?: string; reason?: string; state?: string };
  price?: number;
};

/** --- Fetchers (relative paths so dev proxy works) --- */
async function fetchPositions(): Promise<PositionOut[]> {
  const res = await fetch(`/api/v1/positions`);
  if (!res.ok) throw new Error(`Failed to load positions: ${res.status}`);
  return res.json();
}

async function fetchDetail(symbol: string): Promise<DrawerDetail> {
  const res = await fetch(`/api/v1/instruments/${encodeURIComponent(symbol)}/detail`);
  if (!res.ok) throw new Error(`Failed to load ${symbol} detail: ${res.status}`);
  return res.json();
}

/** --- INR formatting helpers --- */
const inr = (v: number | undefined | null) =>
  typeof v === 'number'
    ? new Intl.NumberFormat('en-IN', {
        style: 'currency',
        currency: 'INR',
        maximumFractionDigits: 2,
      }).format(v)
    : '—';

const pct = (v: number | undefined | null) =>
  typeof v === 'number' && isFinite(v) ? `${v.toFixed(2)}%` : '—';

const num2 = (v: number | undefined | null) =>
  typeof v === 'number' && isFinite(v) ? v.toFixed(2) : '—';

const dt = (v: string | null | undefined) => {
  if (!v) return '?';
  const date = new Date(v);
  return Number.isNaN(date.getTime()) ? '?' : date.toLocaleString();
};

/** Row computed from position + detail */
type Row = {
  id: number;
  symbol: string;
  name?: string;
  lockedEntry?: number;
  qty?: number;
  price?: number; // LTP for active, sell price for closed
  bookValue?: number;
  currentValue?: number;
  pl?: number;
  plPct?: number;
  score?: number;
  nextAction?: string;
  reason?: string;
  status: 'ACTIVE' | 'CLOSED';
  sellPrice?: number | null;
  soldAt?: string | null;
  realizedPl?: number | null;
  realizedPlPct?: number | null;
};

export default function ActiveTradesBoard() {
  const qc = useQueryClient();

  // 1) Load all positions
  const {
    data: positions,
    isLoading: posLoading,
    isFetching: posFetching,
    refetch: refetchPositions,
    error: posError,
  } = useQuery({
    queryKey: ['positions:list'],
    queryFn: fetchPositions,
    staleTime: 60_000,
    refetchOnWindowFocus: true,
  });

  // Only “active trades”: trade_on && entry_price_locked && qty
  const active = React.useMemo(
    () =>
      (positions ?? []).filter(
        (p) =>
          p.trade_on === true &&
          typeof p.entry_price_locked === 'number' &&
          p.entry_price_locked > 0 &&
          typeof p.qty === 'number' &&
          p.qty! > 0
      ),
    [positions]
  );

  // 2) For each active symbol, fetch detail in parallel
  const detailQueries = useQueries({
    queries: active.map((p) => ({
      queryKey: ['detail', p.symbol],
      queryFn: () => fetchDetail(p.symbol),
      staleTime: 60_000,
      refetchOnWindowFocus: true,
      enabled: !!p.symbol,
    })),
  });

  const anyDetailLoading = detailQueries.some((q) => q.isLoading || q.isFetching);
  const detailsBySymbol = React.useMemo(() => {
    const map = new Map<string, DrawerDetail>();
    detailQueries.forEach((q, idx) => {
      const sym = active[idx]?.symbol;
      if (sym && q.data) map.set(sym, q.data);
    });
    return map;
  }, [detailQueries, active]);

  // 3) Compute rows
  const rows: Row[] = React.useMemo(() => {
    if (!positions) return [];

    const sorted = [...positions].sort((a, b) => {
      if (a.trade_on === b.trade_on) {
        const aUpdated = a.updated_at ?? '';
        const bUpdated = b.updated_at ?? '';
        return bUpdated.localeCompare(aUpdated);
      }
      return a.trade_on ? -1 : 1;
    });

    return sorted.map((p) => {
      const isActive = p.trade_on === true;
      const detail = isActive ? detailsBySymbol.get(p.symbol) : undefined;
      const name = detail?.header?.name;

      const entry = typeof p.entry_price_locked === 'number' ? p.entry_price_locked : undefined;
      const qty = typeof p.qty === 'number' ? p.qty : undefined;

      const priceActive = detail ? (detail.header?.price ?? detail.price) : undefined;
      const sellPriceValue = typeof p.sell_price === 'number' ? p.sell_price : undefined;
      const price = isActive ? priceActive : sellPriceValue;

      const bookValue =
        typeof entry === 'number' && typeof qty === 'number' ? entry * qty : undefined;

      let currentValue: number | undefined;
      if (typeof qty === 'number' && typeof price === 'number') {
        currentValue = price * qty;
      }

      let pl: number | undefined;
      let plPct: number | undefined;

      if (isActive) {
        if (typeof currentValue === 'number' && typeof bookValue === 'number') {
          pl = currentValue - bookValue;
        }
        if (typeof entry === 'number' && typeof price === 'number') {
          plPct = (price / entry - 1) * 100;
        }
      } else {
        const realized =
          typeof p.realized_pl === 'number'
            ? p.realized_pl
            : typeof entry === 'number' && typeof sellPriceValue === 'number' && typeof qty === 'number'
            ? (sellPriceValue - entry) * qty
            : undefined;
        const realizedPct =
          typeof p.realized_pl_pct === 'number'
            ? p.realized_pl_pct
            : typeof entry === 'number' && typeof sellPriceValue === 'number'
            ? (sellPriceValue / entry - 1) * 100
            : undefined;
        pl = realized;
        plPct = realizedPct;
      }

      const score =
        isActive && typeof detail?.score_breakdown?.score_total_0_100 === 'number'
          ? detail.score_breakdown!.score_total_0_100
          : isActive && typeof detail?.score === 'number'
          ? detail.score
          : undefined;

      const na = detail?.next_action;
      const nextAction = isActive ? na?.text ?? na?.state ?? na?.reason ?? '' : '';
      const reason = isActive ? na?.reason ?? '' : '';

      const soldAt = !isActive ? (p.sold_at ?? null) : null;
      const realizedPl = !isActive && typeof pl === 'number' ? pl : null;
      const realizedPlPct = !isActive && typeof plPct === 'number' ? plPct : null;

      return {
        id: p.id,
        symbol: p.symbol,
        name,
        lockedEntry: entry,
        qty,
        price,
        bookValue,
        currentValue,
        pl,
        plPct,
        score,
        nextAction,
        reason,
        status: isActive ? 'ACTIVE' : 'CLOSED',
        sellPrice: sellPriceValue ?? null,
        soldAt,
        realizedPl,
        realizedPlPct,
      };
    });
  }, [positions, detailsBySymbol]);

  // 4) Totals for header chips
  const { totalBook, totalCurr, totalPL, totalPLPct } = React.useMemo(() => {
    const activeRows = rows.filter((r) => r.status === 'ACTIVE');
    const accum = activeRows.reduce(
      (acc, r) => {
        if (typeof r.bookValue === 'number') acc.totalBook += r.bookValue;
        if (typeof r.currentValue === 'number') acc.totalCurr += r.currentValue;
        return acc;
      },
      { totalBook: 0, totalCurr: 0 }
    );
    const totalPLCalc =
      isFinite(accum.totalCurr) && isFinite(accum.totalBook)
        ? accum.totalCurr - accum.totalBook
        : undefined;
    const totalPLPctCalc =
      accum.totalBook > 0 ? (accum.totalCurr / accum.totalBook - 1) * 100 : undefined;
    return {
      totalBook: accum.totalBook,
      totalCurr: accum.totalCurr,
      totalPL: totalPLCalc,
      totalPLPct: totalPLPctCalc,
    };
  }, [rows]);

  const plColor =
    typeof totalPL === 'number'
      ? totalPL > 0
        ? 'success'
        : totalPL < 0
        ? 'error'
        : 'default'
      : 'default';

  const refreshAll = async () => {
    await refetchPositions();
    await Promise.all(
      active.map((p) => qc.invalidateQueries({ queryKey: ['detail', p.symbol] }))
    );
  };

  return (
    <Paper sx={{ p: 2 }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
        {/* Title + totals */}
        <Stack direction="row" alignItems="center" gap={1.25}>
          <Typography variant="h6" sx={{ fontWeight: 700 }}>
            Active Trades
          </Typography>

          {/* Total P/L amount */}
          <Chip
            size="small"
            label={`P/L: ${inr(totalPL)}`}
            color={plColor as any}
            variant={plColor === 'default' ? 'outlined' : 'filled'}
            sx={{ fontWeight: 700 }}
          />

          {/* Total P/L % (weighted by book value) */}
          <Chip
            size="small"
            label={`P/L %: ${pct(totalPLPct)}`}
            color={plColor as any}
            variant="outlined"
            sx={{ fontWeight: 700 }}
          />
        </Stack>

        {/* Refresh / loading */}
        <Stack direction="row" alignItems="center" gap={1}>
          {(posLoading || posFetching || anyDetailLoading) && <CircularProgress size={18} />}
          <Tooltip title="Refresh">
            <IconButton onClick={refreshAll} size="small">
              <RefreshIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Stack>
      </Stack>

      {posError ? (
        <Box sx={{ p: 2, color: 'error.main' }}>
          {(posError as Error).message || 'Failed to load positions.'}
        </Box>
      ) : (
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Symbol</TableCell>
              <TableCell>Status</TableCell>
              <TableCell align="right">Entry Price</TableCell>
              <TableCell align="right">Qty</TableCell>
              <TableCell align="right">Book Value</TableCell>
              <TableCell align="right">Price (LTP/Sell)</TableCell>
              <TableCell align="right">Current Value</TableCell>
              <TableCell align="right">Closed At</TableCell>
              <TableCell align="right">P/L (₹)</TableCell>
              <TableCell align="right">P/L %</TableCell>
              <TableCell align="right">Score</TableCell>
              <TableCell>Next Action</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={12} sx={{ color: 'text.secondary' }}>
                  No trades recorded yet.
                </TableCell>
              </TableRow>
            ) : (
              rows.map((r) => {
                const rowColor =
                  typeof r.pl === 'number'
                    ? r.pl > 0
                      ? 'success'
                      : r.pl < 0
                      ? 'error'
                      : 'default'
                    : 'default';
                const statusChipColor = r.status === 'ACTIVE' ? 'success' : 'default';

                return (
                  <TableRow key={r.id} hover>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontWeight: 700 }}>
                        {r.symbol}
                      </Typography>
                      {r.name ? (
                        <Typography variant="caption" color="text.secondary">
                          {r.name}
                        </Typography>
                      ) : null}
                    </TableCell>
                    <TableCell>
                      <Chip
                        size="small"
                        label={r.status === 'ACTIVE' ? 'Active' : 'Closed'}
                        color={statusChipColor as any}
                        variant={r.status === 'ACTIVE' ? 'filled' : 'outlined'}
                      />
                    </TableCell>
                    <TableCell align="right">{num2(r.lockedEntry ?? null)}</TableCell>
                    <TableCell align="right">{r.qty ?? '--'}</TableCell>
                    <TableCell align="right">{inr(r.bookValue)}</TableCell>
                    <TableCell align="right">{num2(r.price ?? null)}</TableCell>
                    <TableCell align="right">{inr(r.currentValue)}</TableCell>
                    <TableCell align="right">{dt(r.soldAt)}</TableCell>
                    <TableCell align="right">
                      {typeof r.pl === 'number' ? (
                        <Chip
                          size="small"
                          label={inr(r.pl)}
                          color={rowColor as any}
                          variant="outlined"
                          sx={{ fontWeight: 700 }}
                        />
                      ) : (
                        '--'
                      )}
                    </TableCell>
                    <TableCell align="right">{pct(r.plPct ?? null)}</TableCell>
                    <TableCell align="right">
                      {r.status === 'ACTIVE' && typeof r.score === 'number' ? r.score.toFixed(0) : '--'}
                    </TableCell>
                    <TableCell>
                      <Stack spacing={0.2}>
                        <Typography variant="body2">
                          {r.status === 'ACTIVE' ? r.nextAction || '--' : 'Closed'}
                        </Typography>
                        {r.status === 'ACTIVE' && r.reason ? (
                          <Typography variant="caption" color="text.secondary">
                            {r.reason}
                          </Typography>
                        ) : null}
                        {r.status === 'CLOSED' && typeof r.realizedPl === 'number' ? (
                          <Typography variant="caption" color="text.secondary">
                            Realized: {inr(r.realizedPl)} ({pct(r.realizedPlPct ?? null)})
                          </Typography>
                        ) : null}
                      </Stack>
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      )}
    </Paper>
  );
}
