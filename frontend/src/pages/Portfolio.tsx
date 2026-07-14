import * as React from 'react';
import {
  Box,
  Button,
  Chip,
  CircularProgress,
  Link,
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
import RefreshIcon from '@mui/icons-material/Refresh';
import axios from 'axios';
import dayjs from 'dayjs';
import { useQuery } from '@tanstack/react-query';
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  ReferenceDot,
  ReferenceLine,
  XAxis,
  YAxis,
  Tooltip as ReTooltip,
  CartesianGrid,
} from 'recharts';
import UsInvestmentsSection from '../features/portfolio/UsInvestmentsSection';
import AddFundTransactionDialog from '../features/portfolio/AddFundTransactionDialog';
import PortfolioAllocation from '../features/portfolio/PortfolioAllocation';
import PortfolioWorkbookPreview from '../features/portfolio/PortfolioWorkbookPreview';
import { buildFundChartSeries, getFundChartDomain } from '../features/portfolio/fundChartData';

type Holding = {
  account_id: string;
  sip_amount: number;
  target_portfolio_pct: number | null;
  accumulation_enabled: boolean;
  units: number;
  invested: number;
  current_value: number | null;
  xirr_pct: number | null;
};

type Instrument = {
  id: string;
  name: string;
  type: string;
  category: string;
  plan: string | null;
  benchmark: string | null;
  links: Record<string, string>;
  scheme_code: string | null;
  scheme_name_resolved: string | null;
  performance: {
    latest_nav?: number;
    latest_nav_date?: string;
    ret_1m_pct?: number | null;
    ret_3m_pct?: number | null;
    ret_6m_pct?: number | null;
    ret_1y_pct?: number | null;
    ret_3y_pct?: number | null;
    drawdown_from_1y_high_pct?: number | null;
  };
  holdings: Holding[];
  totals: {
    units: number;
    invested: number;
    current_value: number | null;
    abs_return_pct: number | null;
    xirr_pct: number | null;
  } | null;
  accumulation: {
    status: string;
    drawdown_from_1y_high_pct: number | null;
    portfolio_weight_pct: number | null;
    target_portfolio_pct: number | null;
    reasons: string[];
  } | null;
  transactions: { date: string; type: string; amount: number; units: number; nav: number; fees: number; invested: number }[];
  combined_holding: { total_units: number; total_invested: number; average_nav: number | null; current_value: number | null; gain: number | null; gain_pct: number | null };
};

type Overview = {
  generated_at: string;
  configured: boolean;
  has_transactions: boolean;
  error?: string;
  summary: {
    total_invested: number | null;
    total_value: number | null;
    abs_return_pct: number | null;
    xirr_pct: number | null;
  };
  allocation: { category: string; value: number; weight_pct: number | null }[];
  instruments: Instrument[];
  notes: string[];
};

const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 });
const pctFmt = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2, signDisplay: 'exceptZero' });

const money = (v?: number | null) => (v == null ? '—' : inr.format(v));
const pct = (v?: number | null) => (v == null ? '—' : `${pctFmt.format(v)}%`);
const tone = (v?: number | null) =>
  v == null ? 'text.secondary' : v > 0 ? 'success.main' : v < 0 ? 'error.main' : 'text.secondary';

const ACCUM_META: Record<string, { label: string; color: 'default' | 'info' | 'warning' | 'success' }> = {
  no_action: { label: 'No action', color: 'default' },
  watch: { label: 'Watch', color: 'info' },
  tranche_eligible: { label: 'Dip: tranche eligible', color: 'warning' },
};

// ---------------------------------------------------------------------------
// NAV history chart (expands under a fund row)
// ---------------------------------------------------------------------------

type NavRange = '1m' | '6m' | '1y' | '5y' | 'max';

type NavHistory = {
  scheme_code: string;
  range: string;
  points: { date: string; nav: number }[];
  first_date?: string;
  last_date?: string;
  change_pct?: number | null;
  inception_date?: string;
  error?: string;
  purchases?: { date: string; amount: number; units: number; nav: number; fees: number; invested: number }[];
  average_nav?: number | null;
  latest_vs_average_pct?: number | null;
};

const NAV_RANGES: { value: NavRange; label: string }[] = [
  { value: '1m', label: '1M' },
  { value: '6m', label: '6M' },
  { value: '1y', label: '1Y' },
  { value: '5y', label: '5Y' },
  { value: 'max', label: 'Since inception' },
];

const FundNavChart: React.FC<{ schemeCode: string; fundName: string; instrumentId: string; transactions: Instrument['transactions'] }> = ({ schemeCode, fundName, instrumentId, transactions }) => {
  const [range, setRange] = React.useState<NavRange>('1y');
  const query = useQuery({
    queryKey: ['nav-history', schemeCode, range],
    queryFn: async () => {
      const res = await axios.get<NavHistory>('/api/v1/portfolio/nav_history', {
        params: { scheme_code: schemeCode, instrument_id: instrumentId, range },
      });
      return res.data;
    },
    staleTime: 30 * 60 * 1000,
    retry: 1,
  });

  const data = query.data;
  const points = data?.points ?? [];
  const spanDays =
    points.length > 1 ? Math.abs(dayjs(points[points.length - 1].date).diff(dayjs(points[0].date), 'day')) : 0;
  const labelFmt = spanDays > 365 ? 'MMM YY' : spanDays > 180 ? 'DD MMM YY' : 'DD MMM';
  const series = buildFundChartSeries(points, data?.purchases ?? []);
  const chartData = series.prices;
  const purchaseData = series.purchases;
  const timeDomain = getFundChartDomain(chartData);
  const changeColor = tone(data?.change_pct);

  return (
    <Box sx={{ py: 1.5, px: { xs: 0.5, md: 1 } }}>
      <Stack direction="row" alignItems="center" spacing={2} flexWrap="wrap" useFlexGap sx={{ mb: 1 }}>
        <Typography variant="body2" fontWeight={700}>
          {fundName} — NAV history
        </Typography>
        {data?.change_pct != null ? (
          <Typography variant="body2" fontWeight={700} color={changeColor}>
            {pct(data.change_pct)} over {NAV_RANGES.find((r) => r.value === range)?.label.toLowerCase()}
          </Typography>
        ) : null}
        {data?.inception_date ? (
          <Typography variant="caption" color="text.secondary">
            inception {dayjs(data.inception_date).format('DD MMM YYYY')}
          </Typography>
        ) : null}
        {data?.latest_vs_average_pct != null ? <Typography variant="body2" color={data.latest_vs_average_pct <= 0 ? 'success.main' : 'warning.main'}>Latest NAV is {Math.abs(data.latest_vs_average_pct).toFixed(2)}% {data.latest_vs_average_pct < 0 ? 'below' : 'above'} average</Typography> : null}
        <Box sx={{ flexGrow: 1 }} />
        <ToggleButtonGroup
          size="small"
          exclusive
          value={range}
          onChange={(_, v: NavRange | null) => {
            if (v) setRange(v);
          }}
        >
          {NAV_RANGES.map((r) => (
            <ToggleButton key={r.value} value={r.value} sx={{ px: 1.25, py: 0.25, textTransform: 'none' }}>
              {r.label}
            </ToggleButton>
          ))}
        </ToggleButtonGroup>
      </Stack>

      {query.isLoading ? (
        <Stack alignItems="center" sx={{ py: 6 }}>
          <CircularProgress size={28} />
        </Stack>
      ) : chartData.length ? (
        <Box sx={{ width: '100%', height: 280 }}>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e6e8ee" vertical={false} />
              <XAxis dataKey="time" type="number" scale="time" domain={timeDomain} allowDataOverflow tick={{ fontSize: 11 }} minTickGap={40} tickMargin={6} tickFormatter={(value: number) => dayjs(value).format(labelFmt)} />
              <YAxis
                tick={{ fontSize: 11 }}
                width={64}
                domain={['auto', 'auto']}
                tickFormatter={(v: number) => v.toFixed(v >= 1000 ? 0 : 1)}
              />
              <ReTooltip
                formatter={(v: any) => [Number(v).toFixed(2), 'NAV']}
                labelFormatter={(value: any) => dayjs(Number(value)).format('DD MMM YYYY')}
              />
              <Line type="monotone" dataKey="nav" stroke="#2f80ed" strokeWidth={1.6} dot={false} isAnimationActive={false} />
              {purchaseData.map((purchase: any, index: number) => (
                <ReferenceDot
                  key={`${purchase.time}-${index}`}
                  x={purchase.time}
                  y={purchase.purchaseNav}
                  r={5}
                  fill="#f59e0b"
                  stroke="#f59e0b"
                  ifOverflow="hidden"
                />
              ))}
              {data?.average_nav != null ? <ReferenceLine y={data.average_nav} stroke="#8b5cf6" strokeDasharray="6 4" label={{ value: `Avg ${data.average_nav.toFixed(2)}`, position: 'insideTopRight' }} /> : null}
            </ComposedChart>
          </ResponsiveContainer>
        </Box>
      ) : (
        <Typography variant="body2" color="text.secondary" sx={{ py: 4, textAlign: 'center' }}>
          {data?.error ? 'No NAV history available for this fund.' : 'No data for this range.'}
        </Typography>
      )}
      {transactions.length ? <Table size="small" sx={{ mt: 1 }}><TableHead><TableRow><TableCell>Date</TableCell><TableCell align="right">Units</TableCell><TableCell align="right">NAV</TableCell><TableCell align="right">Fees</TableCell><TableCell align="right">Invested</TableCell></TableRow></TableHead><TableBody>{transactions.map((t, i) => <TableRow key={`${t.date}-${i}`}><TableCell>{dayjs(t.date).format('DD MMM YYYY')}</TableCell><TableCell align="right">{t.units}</TableCell><TableCell align="right">{t.nav}</TableCell><TableCell align="right">{money(t.fees)}</TableCell><TableCell align="right">{money(t.invested)}</TableCell></TableRow>)}</TableBody></Table> : <Typography variant="caption" color="text.secondary">Add your first purchase to compare against NAV history.</Typography>}
    </Box>
  );
};

const Portfolio: React.FC = () => {
  const [refreshing, setRefreshing] = React.useState(false);
  const [expandedFund, setExpandedFund] = React.useState<string | null>(null);
  const [transactionFund, setTransactionFund] = React.useState<Instrument | null>(null);
  const query = useQuery({
    queryKey: ['portfolio-overview'],
    queryFn: async () => {
      const res = await axios.get<Overview>('/api/v1/portfolio/overview');
      return res.data;
    },
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });

  const forceRefresh = async () => {
    setRefreshing(true);
    try {
      await axios.get('/api/v1/portfolio/overview', { params: { refresh: true } });
      await query.refetch();
    } finally {
      setRefreshing(false);
    }
  };

  const data = query.data;

  if (query.isLoading) {
    return (
      <Stack alignItems="center" sx={{ py: 6 }}>
        <CircularProgress />
      </Stack>
    );
  }

  if (!data || !data.configured) {
    return (
      <Paper sx={{ p: 3, mx: 2 }}>
        <Typography variant="h6">Portfolio not configured</Typography>
        <Typography variant="body2" color="text.secondary">
          {data?.error ?? 'Add configs/portfolio.yaml to define your funds and accounts.'}
        </Typography>
      </Paper>
    );
  }

  const funds = data.instruments.filter((i) => i.type === 'mutual_fund');
  const others = data.instruments.filter((i) => i.type !== 'mutual_fund');
  const opportunities = funds.filter(
    (f) => f.accumulation && f.accumulation.status !== 'no_action'
  );

  return (
    <Stack spacing={2} sx={{ px: 2 }}>
      {/* Summary strip */}
      <Paper variant="outlined" sx={{ overflow: 'hidden' }}>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2.5} alignItems={{ md: 'center' }} flexWrap="wrap" useFlexGap sx={{ px: 2, py: 1.5 }}>
          <Box sx={{ minWidth: 190 }}>
            <Typography variant="h6" sx={{ fontWeight: 800 }}>Portfolio</Typography>
            <Typography variant="caption" color="text.secondary">Maintain, compare and grow</Typography>
          </Box>
          <SummaryItem label="Principal invested" value={money(data.summary.total_invested)} />
          <SummaryItem label="Current market value" value={money(data.summary.total_value)} />
          <SummaryItem
            label="Absolute return"
            value={pct(data.summary.abs_return_pct)}
            color={tone(data.summary.abs_return_pct)}
          />
          <SummaryItem label="XIRR" value={pct(data.summary.xirr_pct)} color={tone(data.summary.xirr_pct)} />
          <Box sx={{ flexGrow: 1 }} />
          <Button size="small" startIcon={<RefreshIcon />} onClick={forceRefresh} disabled={refreshing}>
            {refreshing ? 'Refreshing NAVs…' : 'Refresh NAVs'}
          </Button>
        </Stack>
        {!data.has_transactions ? (
          <Typography variant="caption" color="warning.main" sx={{ display: 'block', px: 2, py: 1, bgcolor: 'warning.50', borderTop: '1px solid', borderColor: 'divider' }}>
            No transactions yet — fill data/portfolio_transactions.csv to see invested value, XIRR and allocation.
            Fund performance and dip signals below work without it.
          </Typography>
        ) : null}
      </Paper>

      {/* Allocation */}
      {data.allocation.length ? (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 0.5 }}>
            Allocation by category
          </Typography>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>Invested amount across mutual-fund categories</Typography>
          <PortfolioAllocation allocation={data.allocation} />
        </Paper>
      ) : null}

      {/* Accumulation opportunities */}
      <Paper sx={{ p: 2 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1 }}>
          Accumulation signals (dip / underweight)
        </Typography>
        {opportunities.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            No funds currently in the configured dip zone.
          </Typography>
        ) : (
          <Stack spacing={1}>
            {opportunities.map((f) => (
              <Box key={f.id} sx={{ display: 'flex', gap: 1, alignItems: 'baseline', flexWrap: 'wrap' }}>
                <Chip
                  size="small"
                  color={ACCUM_META[f.accumulation!.status]?.color ?? 'default'}
                  label={ACCUM_META[f.accumulation!.status]?.label ?? f.accumulation!.status}
                />
                <Typography variant="body2" fontWeight={600}>
                  {f.name}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {f.accumulation!.reasons.join(' • ')}
                </Typography>
              </Box>
            ))}
          </Stack>
        )}
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
          Rule-based signals from NAV drawdown and target allocation — information, not advice.
        </Typography>
      </Paper>

      {/* Funds table */}
      <Paper sx={{ p: 2, overflowX: 'auto' }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1 }}>
          Funds
        </Typography>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Fund</TableCell>
              <TableCell>Category</TableCell>
              <TableCell align="right">NAV</TableCell>
              <TableCell align="right">1M</TableCell>
              <TableCell align="right">6M</TableCell>
              <TableCell align="right">1Y</TableCell>
              <TableCell align="right">Off 1Y high</TableCell>
              <TableCell align="right">Invested</TableCell>
              <TableCell align="right">Value</TableCell>
              <TableCell align="right">XIRR</TableCell>
              <TableCell align="right">Avg NAV</TableCell>
              <TableCell align="right">Gain / loss</TableCell>
              <TableCell align="center">Action</TableCell>
              <TableCell align="center">Links</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {funds.map((f) => {
              const perf = f.performance || {};
              const expanded = expandedFund === f.id;
              const canChart = !!f.scheme_code;
              return (
                <React.Fragment key={f.id}>
                <TableRow
                  hover
                  selected={expanded}
                  onClick={() => {
                    if (canChart) setExpandedFund(expanded ? null : f.id);
                  }}
                  sx={{ cursor: canChart ? 'pointer' : 'default' }}
                >
                  <TableCell>
                    <Tooltip title={f.scheme_name_resolved ?? f.name}>
                      <Typography variant="body2" fontWeight={600}>
                        {f.name}
                      </Typography>
                    </Tooltip>
                    {f.holdings.length > 1 ? (
                      <Typography variant="caption" color="text.secondary">
                        {f.holdings.map((h) => h.account_id).join(', ')}
                      </Typography>
                    ) : (
                      <Typography variant="caption" color="text.secondary">
                        {f.holdings[0]?.account_id ?? ''}
                      </Typography>
                    )}
                  </TableCell>
                  <TableCell>
                    <Chip size="small" variant="outlined" label={f.category} />
                  </TableCell>
                  <TableCell align="right">
                    {perf.latest_nav != null ? (
                      <Tooltip title={`as of ${perf.latest_nav_date ? dayjs(perf.latest_nav_date).format('DD MMM YYYY') : '—'}`}>
                        <span>{perf.latest_nav.toFixed(2)}</span>
                      </Tooltip>
                    ) : (
                      '—'
                    )}
                  </TableCell>
                  <TableCell align="right" sx={{ color: tone(perf.ret_1m_pct) }}>{pct(perf.ret_1m_pct)}</TableCell>
                  <TableCell align="right" sx={{ color: tone(perf.ret_6m_pct) }}>{pct(perf.ret_6m_pct)}</TableCell>
                  <TableCell align="right" sx={{ color: tone(perf.ret_1y_pct) }}>{pct(perf.ret_1y_pct)}</TableCell>
                  <TableCell align="right" sx={{ color: tone(perf.drawdown_from_1y_high_pct) }}>
                    {pct(perf.drawdown_from_1y_high_pct)}
                  </TableCell>
                  <TableCell align="right">{f.totals ? money(f.totals.invested) : '—'}</TableCell>
                  <TableCell align="right">{f.totals ? money(f.totals.current_value) : '—'}</TableCell>
                  <TableCell align="right" sx={{ color: tone(f.totals?.xirr_pct) }}>
                    {pct(f.totals?.xirr_pct)}
                  </TableCell>
                  <TableCell align="right">{f.combined_holding?.average_nav?.toFixed(2) ?? '—'}</TableCell>
                  <TableCell align="right" sx={{ color: tone(f.combined_holding?.gain_pct) }}>{money(f.combined_holding?.gain)} {f.combined_holding?.gain_pct != null ? `(${pct(f.combined_holding.gain_pct)})` : ''}</TableCell>
                  <TableCell align="center"><Button size="small" onClick={e => { e.stopPropagation(); setTransactionFund(f); }}>Add transaction</Button></TableCell>
                  <TableCell align="center">
                    {Object.entries(f.links || {}).map(([k, url]) => (
                      <Tooltip key={k} title={k}>
                        <Link
                          href={url}
                          target="_blank"
                          rel="noopener"
                          sx={{ mx: 0.25 }}
                          onClick={(e) => e.stopPropagation()}
                        >
                          <OpenInNewIcon fontSize="inherit" />
                        </Link>
                      </Tooltip>
                    ))}
                  </TableCell>
                </TableRow>
                {expanded && canChart ? (
                  <TableRow>
                    <TableCell colSpan={14} sx={{ p: 0, borderBottom: '2px solid', borderColor: 'divider', bgcolor: 'action.hover' }}>
                      <FundNavChart schemeCode={f.scheme_code!} fundName={f.name} instrumentId={f.id} transactions={f.transactions ?? []} />
                    </TableCell>
                  </TableRow>
                ) : null}
                </React.Fragment>
              );
            })}
          </TableBody>
        </Table>
      </Paper>

      <UsInvestmentsSection />
      {transactionFund ? <AddFundTransactionDialog open fundId={transactionFund.id} fundName={transactionFund.name} onClose={() => setTransactionFund(null)} onSaved={async () => { await query.refetch(); }} /> : null}

      {others.length ? (
        <Paper sx={{ p: 2 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1 }}>
            Other instruments
          </Typography>
          {others.map((o) => (
            <Typography key={o.id} variant="body2" color="text.secondary">
              {o.name} ({o.category}) {o.totals ? `— invested ${money(o.totals.invested)}` : '— add transactions to track'}
            </Typography>
          ))}
        </Paper>
      ) : null}

      <PortfolioWorkbookPreview />

      <Typography variant="caption" color="text.secondary" sx={{ pb: 2 }}>
        {data.notes.join(' ')} Generated {dayjs(data.generated_at).format('DD MMM YYYY, HH:mm')}.
      </Typography>
    </Stack>
  );
};

const SummaryItem: React.FC<{ label: string; value: string; color?: string }> = ({ label, value, color }) => (
  <Box sx={{ minWidth: 130 }}>
    <Typography variant="overline" color="text.secondary" display="block" lineHeight={1.2}>
      {label}
    </Typography>
    <Typography variant="h6" fontWeight={700} color={color}>
      {value}
    </Typography>
  </Box>
);

export default Portfolio;
