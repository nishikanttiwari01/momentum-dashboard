import * as React from 'react';
import {
  Box,
  CircularProgress,
  IconButton,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from '@mui/material';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import dayjs from 'dayjs';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip as ReTooltip,
  CartesianGrid,
  ReferenceLine,
  ReferenceDot,
} from 'recharts';
import type { SparklineRange } from '@/features/detail/SparklineRe';
import { displaySymbol } from '@/lib/formatters';

const inr = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 });
const pctFmt = new Intl.NumberFormat('en-US', { maximumFractionDigits: 1, signDisplay: 'exceptZero' });
const money = (v?: number) => (v == null || !Number.isFinite(v) ? '—' : inr.format(v));
const tone = (v?: number) =>
  v == null ? 'text.secondary' : v > 0 ? 'success.main' : v < 0 ? 'error.main' : 'text.secondary';

export type PositionRow = {
  id: string | number;
  symbol: string;
  qty?: number;
  entry?: number;
  ltp?: number;
  invested?: number;
  current?: number;
  pl?: number;
  plPct?: number;
  createdAt?: string;
  stop?: number;
  isFetching?: boolean;
  sparkPrices?: number[];
  sparkDates?: string[];
};

type Props = {
  rows: PositionRow[];
  loading?: boolean;
  error?: boolean;
  rangeForSymbol: (symbol: string) => SparklineRange;
  onRangeChange: (symbol: string, r: SparklineRange) => void;
  onOpenDrawer: (symbol: string) => void;
};

const RANGES: SparklineRange[] = ['30d', '3m', '1y'];

const rangeDays: Record<SparklineRange, number> = { '30d': 30, '3m': 92, '1y': 366, '5y': 1830 };
const smallestRangeCovering = (daysHeld: number): SparklineRange =>
  daysHeld <= 30 ? '30d' : daysHeld <= 92 ? '3m' : '1y';

const TradePositionsPanel: React.FC<Props> = ({ rows, loading, error, rangeForSymbol, onRangeChange, onOpenDrawer }) => {
  const [selected, setSelected] = React.useState<string | null>(null);
  const sel = rows.find((r) => r.symbol === selected) ?? rows[0];

  // Default the chart range so the buy point is visible (only once per symbol —
  // after that the user's manual range choice is respected).
  const autoRanged = React.useRef<Set<string>>(new Set());
  React.useEffect(() => {
    if (!sel?.symbol || !sel.createdAt) return;
    if (autoRanged.current.has(sel.symbol)) return;
    const held = dayjs().diff(dayjs(sel.createdAt), 'day');
    const needed = smallestRangeCovering(held);
    if (rangeDays[needed] > rangeDays[rangeForSymbol(sel.symbol)]) {
      onRangeChange(sel.symbol, needed);
    }
    autoRanged.current.add(sel.symbol);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sel?.symbol]);

  const totals = React.useMemo(() => {
    const pl = rows.reduce((s, r) => s + (r.pl ?? 0), 0);
    const invested = rows.reduce((s, r) => s + (r.invested ?? 0), 0);
    const withPct = rows.filter((r) => r.plPct != null);
    const best = withPct.length ? withPct.reduce((a, b) => ((a.plPct ?? -1e9) >= (b.plPct ?? -1e9) ? a : b)) : undefined;
    const worst = withPct.length ? withPct.reduce((a, b) => ((a.plPct ?? 1e9) <= (b.plPct ?? 1e9) ? a : b)) : undefined;
    return { pl, invested, best, worst };
  }, [rows]);

  const chart = React.useMemo(() => {
    if (!sel?.sparkPrices?.length) return null;
    const dates = sel.sparkDates ?? [];
    const spanDays =
      dates.length > 1 ? Math.abs(dayjs(dates[dates.length - 1]).diff(dayjs(dates[0]), 'day')) : 0;
    const fmt = spanDays > 180 ? 'DD MMM YY' : 'DD MMM';
    const data: any[] = sel.sparkPrices.map((p, i) => ({
      i,
      label: dates[i] ? dayjs(dates[i]).format(fmt) : `${i}`,
      price: p,
      buy: null as number | null,
    }));
    // buy marker: entry date within visible range → dot at nearest bar
    let buyIdx: number | null = null;
    if (sel.createdAt && dates.length) {
      const created = dayjs(sel.createdAt);
      if (
        created.isValid() &&
        !created.isBefore(dayjs(dates[0]), 'day') &&
        !created.isAfter(dayjs(dates[dates.length - 1]), 'day')
      ) {
        let bestI = 0;
        let bestD = Infinity;
        dates.forEach((d, i) => {
          const diff = Math.abs(dayjs(d).diff(created, 'day'));
          if (diff < bestD) {
            bestD = diff;
            bestI = i;
          }
        });
        buyIdx = bestI;
      }
    }
    // buy happened before the visible window → pin marker at the left edge
    const buyBeforeWindow =
      buyIdx == null &&
      sel.createdAt != null &&
      dates.length > 0 &&
      dayjs(sel.createdAt).isValid() &&
      dayjs(sel.createdAt).isBefore(dayjs(dates[0]), 'day');
    // buy marker rendered as its own series — reliable across recharts versions
    if (sel.entry != null) {
      const markIdx = buyIdx != null ? buyIdx : buyBeforeWindow ? 0 : null;
      if (markIdx != null && data[markIdx]) data[markIdx].buy = sel.entry;
    }
    const ys = data.map((d) => d.price).filter(Number.isFinite);
    if (sel.entry != null) ys.push(sel.entry);
    if (sel.stop != null) ys.push(sel.stop);
    const min = Math.min(...ys);
    const max = Math.max(...ys);
    const pad = (max - min || 1) * 0.06;
    return { data, buyIdx, buyBeforeWindow, domain: [Math.floor(min - pad), Math.ceil(max + pad)] as [number, number] };
  }, [sel]);

  return (
    <Paper sx={{ p: 2, width: '100%', height: '100%' }}>
      {/* KPI strip */}
      <Stack direction="row" spacing={5} sx={{ mb: 1.5, flexWrap: 'wrap', rowGap: 1 }}>
        <Kpi label="Open P/L" value={`${totals.pl < 0 ? '−' : '+'}₹${money(Math.abs(totals.pl))}`} color={tone(totals.pl)} sub={`${rows.length} position${rows.length === 1 ? '' : 's'}`} />
        <Kpi label="Deployed" value={`₹${money(totals.invested)}`} sub="at entry price" />
        {totals.best ? (
          <Kpi label="Best" value={`${displaySymbol(totals.best.symbol)} ${pctFmt.format(totals.best.plPct!)}%`} color="success.main" />
        ) : null}
        {totals.worst ? (
          <Kpi label="Worst" value={`${displaySymbol(totals.worst.symbol)} ${pctFmt.format(totals.worst.plPct!)}%`} color="error.main" />
        ) : null}
      </Stack>

      {error ? (
        <Typography color="error">Unable to load active trades right now.</Typography>
      ) : loading ? (
        <Stack alignItems="center" sx={{ py: 4 }}>
          <CircularProgress size={24} />
        </Stack>
      ) : rows.length === 0 ? (
        <Typography color="text.secondary" sx={{ py: 2 }}>
          No active trades to display.
        </Typography>
      ) : (
        <>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Symbol</TableCell>
                <TableCell align="right">Qty@Entry</TableCell>
                <TableCell align="right">LTP</TableCell>
                <TableCell align="right">Invested</TableCell>
                <TableCell align="right">P/L</TableCell>
                <TableCell align="right">P/L%</TableCell>
                <TableCell align="center" sx={{ width: 42 }} />
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((r) => {
                const isSel = sel?.symbol === r.symbol;
                return (
                  <TableRow
                    key={r.id}
                    hover
                    onClick={() => setSelected(r.symbol)}
                    sx={{ cursor: 'pointer', bgcolor: isSel ? '#F4F9FF' : undefined }}
                  >
                    <TableCell>
                      <Typography variant="body2" fontWeight={600}>
                        {isSel ? '▸ ' : ''}
                        {displaySymbol(r.symbol)}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        since {r.createdAt ? dayjs(r.createdAt).format('DD MMM YY') : '—'}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">{r.qty ?? '—'}@{r.entry != null ? inr.format(r.entry) : '—'}</TableCell>
                    <TableCell align="right">
                      {r.ltp != null ? inr.format(r.ltp) : r.isFetching ? <CircularProgress size={12} /> : '—'}
                    </TableCell>
                    <TableCell align="right">{money(r.invested)}</TableCell>
                    <TableCell align="right" sx={{ color: tone(r.pl), fontWeight: 600 }}>
                      {r.pl != null ? `${r.pl < 0 ? '−' : '+'}${money(Math.abs(r.pl))}` : '—'}
                    </TableCell>
                    <TableCell align="right" sx={{ color: tone(r.plPct), fontWeight: 600 }}>
                      {r.plPct != null ? pctFmt.format(r.plPct) : '—'}
                    </TableCell>
                    <TableCell align="center">
                      <Tooltip title="Open full detail">
                        <IconButton
                          size="small"
                          onClick={(e) => {
                            e.stopPropagation();
                            onOpenDrawer(r.symbol);
                          }}
                        >
                          <OpenInNewIcon sx={{ fontSize: 15 }} />
                        </IconButton>
                      </Tooltip>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>

          {sel ? (
            <Box sx={{ mt: 1.5 }}>
              <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 0.5, flexWrap: 'wrap' }}>
                <Typography variant="caption" color="text.secondary">
                  {displaySymbol(sel.symbol)} · entry — grey · stop ┄ red ·{' '}
                  <Box component="span" sx={{ color: '#00B386' }}>
                    ● bought
                  </Box>
                </Typography>
                <Box sx={{ flexGrow: 1 }} />
                <ToggleButtonGroup
                  size="small"
                  exclusive
                  value={rangeForSymbol(sel.symbol)}
                  onChange={(_, v) => v && onRangeChange(sel.symbol, v)}
                >
                  {RANGES.map((r) => (
                    <ToggleButton key={r} value={r}>
                      {r}
                    </ToggleButton>
                  ))}
                </ToggleButtonGroup>
              </Stack>
              {chart ? (
                <Box sx={{ height: 260 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chart.data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
                      <CartesianGrid stroke="#F5F5F5" vertical={false} />
                      <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#9b9b9b' }} minTickGap={40} tickLine={false} axisLine={{ stroke: '#ECECEC' }} />
                      <YAxis domain={chart.domain} tick={{ fontSize: 10, fill: '#9b9b9b' }} width={48} tickLine={false} axisLine={{ stroke: '#ECECEC' }} />
                      <ReTooltip
                        formatter={(v: any, name: any) =>
                          name === 'Bought'
                            ? [`₹${inr.format(Number(v))} × ${sel.qty ?? '—'} on ${sel.createdAt ? dayjs(sel.createdAt).format('DD MMM YY') : '—'}`, 'Bought']
                            : [`₹${inr.format(Number(v))}`, 'Price']
                        }
                        labelStyle={{ fontSize: 12 }}
                        contentStyle={{ fontSize: 12, borderRadius: 6, border: '1px solid #ECECEC' }}
                      />
                      {sel.entry != null ? (
                        <ReferenceLine y={sel.entry} stroke="#B0B4BE" strokeDasharray="5 4" label={{ value: `entry ${inr.format(sel.entry)}`, position: 'insideTopRight', fontSize: 10, fill: '#9b9b9b' }} />
                      ) : null}
                      {sel.stop != null ? (
                        <ReferenceLine y={sel.stop} stroke="#F04438" strokeDasharray="5 4" label={{ value: `stop ${inr.format(sel.stop)}`, position: 'insideBottomRight', fontSize: 10, fill: '#F04438' }} />
                      ) : null}
                      <Line type="monotone" dataKey="price" stroke="#2E90FA" strokeWidth={1.8} dot={false} isAnimationActive={false} />
                      <Line
                        dataKey="buy"
                        stroke="none"
                        isAnimationActive={false}
                        connectNulls={false}
                        dot={{ r: 7, fill: '#00B386', stroke: '#fff', strokeWidth: 2 }}
                        activeDot={{ r: 8, fill: '#00B386', stroke: '#fff', strokeWidth: 2 }}
                        name="Bought"
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </Box>
              ) : (
                <Typography variant="caption" color="text.secondary">
                  {sel.isFetching ? 'Loading chart…' : 'No chart data for this range.'}
                </Typography>
              )}
              {chart && sel.entry != null && !chart.buyBeforeWindow && chart.buyIdx != null ? (
                <Typography variant="caption" sx={{ color: '#00B386' }}>
                  ● bought {sel.qty ?? ''} @ ₹{inr.format(sel.entry)} on {sel.createdAt ? dayjs(sel.createdAt).format('DD MMM YY') : '—'}
                </Typography>
              ) : null}
              {chart && chart.buyBeforeWindow && sel.createdAt ? (
                <Typography variant="caption" sx={{ color: '#00B386' }}>
                  ● bought {dayjs(sel.createdAt).format('DD MMM YY')} — before this window; marker pinned at the left edge.{' '}
                  <Box component="span" sx={{ color: 'text.secondary' }}>
                    Pick a longer range for the exact spot.
                  </Box>
                </Typography>
              ) : null}
            </Box>
          ) : null}
        </>
      )}
    </Paper>
  );
};

const Kpi: React.FC<{ label: string; value: string; sub?: string; color?: string }> = ({ label, value, sub, color }) => (
  <Box sx={{ minWidth: 110 }}>
    <Typography sx={{ fontSize: 11, color: 'text.secondary', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
      {label}
    </Typography>
    <Typography sx={{ fontFamily: 'Poppins, Inter, sans-serif', fontSize: 20, fontWeight: 600, color, fontVariantNumeric: 'tabular-nums' }}>
      {value}
    </Typography>
    {sub ? (
      <Typography sx={{ fontSize: 11.5, color: 'text.secondary' }}>{sub}</Typography>
    ) : null}
  </Box>
);

export default TradePositionsPanel;
