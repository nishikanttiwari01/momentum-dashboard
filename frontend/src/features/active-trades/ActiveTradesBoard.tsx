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

/** Row computed from position + detail */
type Row = {
  id: number;
  symbol: string;
  name?: string;
  lockedEntry?: number;
  qty?: number;
  ltp?: number; // last traded/current price
  bookValue?: number;
  currentValue?: number;
  pl?: number;
  plPct?: number;
  score?: number;
  nextAction?: string;
  reason?: string;
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
    return active.map((p) => {
      const d = detailsBySymbol.get(p.symbol);
      const name = d?.header?.name;
      const ltp = (d?.header?.price ?? d?.price) as number | undefined;
      const lockedEntry = p.entry_price_locked ?? undefined;
      const qty = p.qty ?? undefined;

      const bookValue =
        typeof lockedEntry === 'number' && typeof qty === 'number'
          ? lockedEntry * qty
          : undefined;

      const currentValue =
        typeof ltp === 'number' && typeof qty === 'number' ? ltp * qty : undefined;

      const pl =
        typeof currentValue === 'number' && typeof bookValue === 'number'
          ? currentValue - bookValue
          : undefined;

      const plPct =
        typeof lockedEntry === 'number' && typeof ltp === 'number'
          ? (ltp / lockedEntry - 1) * 100
          : undefined;

      const score =
        typeof d?.score_breakdown?.score_total_0_100 === 'number'
          ? d!.score_breakdown!.score_total_0_100
          : typeof d?.score === 'number'
          ? d!.score
          : undefined;

      const na = d?.next_action;
      const nextAction = na?.text ?? na?.state ?? na?.reason ?? '';
      const reason = na?.reason ?? '';

      return {
        id: p.id,
        symbol: p.symbol,
        name,
        lockedEntry,
        qty,
        ltp,
        bookValue,
        currentValue,
        pl,
        plPct,
        score,
        nextAction,
        reason,
      };
    });
  }, [active, detailsBySymbol]);

  // 4) Totals for header chips
  const { totalBook, totalCurr, totalPL, totalPLPct } = React.useMemo(() => {
    const vals = rows.reduce(
      (acc, r) => {
        if (typeof r.bookValue === 'number') acc.totalBook += r.bookValue;
        if (typeof r.currentValue === 'number') acc.totalCurr += r.currentValue;
        return acc;
      },
      { totalBook: 0, totalCurr: 0 }
    );
    const totalPLCalc =
      isFinite(vals.totalCurr) && isFinite(vals.totalBook)
        ? vals.totalCurr - vals.totalBook
        : undefined;
    const totalPLPctCalc =
      vals.totalBook > 0 ? (vals.totalCurr / vals.totalBook - 1) * 100 : undefined;
    return {
      totalBook: vals.totalBook,
      totalCurr: vals.totalCurr,
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
              <TableCell align="right">Locked Entry</TableCell>
              <TableCell align="right">Qty</TableCell>
              <TableCell align="right">Book Value</TableCell>
              <TableCell align="right">LTP</TableCell>
              <TableCell align="right">Current Value</TableCell>
              <TableCell align="right">P/L (₹)</TableCell>
              <TableCell align="right">P/L %</TableCell>
              <TableCell align="right">Score</TableCell>
              <TableCell>Next Action</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={10} sx={{ color: 'text.secondary' }}>
                  No active trades yet.
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

                return (
                  <TableRow key={r.id} hover>
                    {/* Symbol — secondary line removed */}
                    <TableCell>
                      <Typography variant="body2" sx={{ fontWeight: 700 }}>
                        {r.symbol}
                      </Typography>
                    </TableCell>

                    <TableCell align="right">{num2(r.lockedEntry ?? null)}</TableCell>
                    <TableCell align="right">{r.qty ?? '—'}</TableCell>
                    <TableCell align="right">{inr(r.bookValue)}</TableCell>
                    <TableCell align="right">{num2(r.ltp ?? null)}</TableCell>
                    <TableCell align="right">{inr(r.currentValue)}</TableCell>
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
                        '—'
                      )}
                    </TableCell>
                    <TableCell align="right">{pct(r.plPct ?? null)}</TableCell>
                    <TableCell align="right">
                      {typeof r.score === 'number' ? r.score.toFixed(0) : '—'}
                    </TableCell>
                    <TableCell>
                      <Stack spacing={0.2}>
                        <Typography variant="body2">{r.nextAction || '—'}</Typography>
                        {r.reason ? (
                          <Typography variant="caption" color="text.secondary">
                            {r.reason}
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
