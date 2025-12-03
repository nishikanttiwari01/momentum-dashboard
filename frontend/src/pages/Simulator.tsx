import * as React from 'react';
import axios from 'axios';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  Grid,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

type SimulationParamsPayload = {
  min_score?: number;
  min_adx?: number;
  atr_pct_min?: number;
  atr_pct_max?: number;
  prox52w_min_pct?: number;
  pivot_clear_min_pct?: number;
  pivot_clear_max_pct?: number;
  base_len_min_bars?: number;
  relvol20_min?: number;
  day_change_max_pct?: number;
  liquidity_min?: number;
  stop_loss_pct?: number;
  max_hold_days?: number | null;
  top_n?: number | null;
  first_trade_only?: boolean;
};

type TradeOut = {
  symbol: string;
  entry_date: string;
  exit_date: string;
  entry_price: number;
  exit_price: number;
  pnl_pct: number;
  holding_days: number;
  notes?: string | null;
};

type SeriesPoint = { date: string; close: number | null };

type SimulationRun = {
  label: string;
  params: SimulationParamsPayload;
  summary: Record<string, number>;
  trades: TradeOut[];
  charts: Record<string, SeriesPoint[]>;
};

type SimulationResponse = { runs: SimulationRun[] };

const formatPct = (v?: number) => (v == null ? '--' : `${v.toFixed(2)}%`);

const defaultStart = () => '2025-10-01';
const defaultEnd = () => '2025-10-31';

const Chart: React.FC<{ points: SeriesPoint[]; trade: TradeOut }> = ({ points, trade }) => {
  const buy = points.find((p) => p.date === trade.entry_date);
  const sell = points.find((p) => p.date === trade.exit_date);
  const formatted = points.map((p) => ({ ...p, close: p.close ?? 0 }));

  return (
    <Box sx={{ height: 200 }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={formatted} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="date" tick={{ fontSize: 10 }} minTickGap={24} />
          <YAxis tick={{ fontSize: 10 }} width={50} />
          <Tooltip formatter={(val: number) => val.toFixed(2)} />
          <Line type="monotone" dataKey="close" stroke="#1976d2" dot={false} strokeWidth={1.2} />
          {buy ? <ReferenceDot x={buy.date} y={trade.entry_price} r={5} fill="#2e7d32" stroke="none" /> : null}
          {sell ? <ReferenceDot x={sell.date} y={trade.exit_price} r={5} fill="#d32f2f" stroke="none" /> : null}
        </LineChart>
      </ResponsiveContainer>
    </Box>
  );
};

export default function Simulator() {
  const [startDate, setStartDate] = React.useState(defaultStart);
  const [endDate, setEndDate] = React.useState(defaultEnd);
  const [params, setParams] = React.useState<SimulationParamsPayload>({
    min_score: 70,
    min_adx: 22,
    atr_pct_min: 2,
    atr_pct_max: 8,
    prox52w_min_pct: -8,
    pivot_clear_min_pct: -0.3,
    pivot_clear_max_pct: 6,
    base_len_min_bars: 5,
    relvol20_min: 1.3,
    day_change_max_pct: 6,
    liquidity_min: 50_000_000,
    stop_loss_pct: 0.05,
    max_hold_days: 25,
    top_n: 10,
    first_trade_only: true,
  });
  const [manualSymbols, setManualSymbols] = React.useState('');
  const [autoSweep, setAutoSweep] = React.useState(true);
  const [runs, setRuns] = React.useState<SimulationRun[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const buildVariants = React.useCallback((): SimulationParamsPayload[] => {
    if (!autoSweep) return [];
    return [
      { ...params, stop_loss_pct: (params.stop_loss_pct || 0.05) - 0.02, max_hold_days: (params.max_hold_days || 25) - 5 },
      { ...params, min_score: (params.min_score || 70) - 2, min_adx: (params.min_adx || 22) + 3 },
      { ...params, atr_pct_max: (params.atr_pct_max || 8) - 1, first_trade_only: false },
    ];
  }, [autoSweep, params]);

  const handleRun = async () => {
    setLoading(true);
    setError(null);
    try {
      const manual = manualSymbols
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
      const body = {
        start_date: startDate,
        end_date: endDate,
        params,
        variants: buildVariants(),
        manual_symbols: manual.length ? manual : undefined,
      };
      const resp = await axios.post<SimulationResponse>('/api/v1/simulator/run', body);
      setRuns(resp.data.runs || []);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || 'Failed to run simulator');
    } finally {
      setLoading(false);
    }
  };

  const best = runs[0];
  const top3 = runs.slice(0, 3);

  return (
    <Stack spacing={2}>
      <Typography variant="h5" fontWeight={800}>
        Simulator
      </Typography>
      <Card>
        <CardContent>
          <Grid container spacing={2}>
            <Grid item xs={12} sm={6} md={2}>
              <TextField
                label="Start date"
                type="date"
                fullWidth
                size="small"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                InputLabelProps={{ shrink: true }}
              />
            </Grid>
            <Grid item xs={12} sm={6} md={2}>
              <TextField
                label="End date"
                type="date"
                fullWidth
                size="small"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                InputLabelProps={{ shrink: true }}
              />
            </Grid>
            <Grid item xs={12} sm={6} md={2}>
              <TextField
                label="Min score"
                type="number"
                fullWidth
                size="small"
                value={params.min_score ?? ''}
                onChange={(e) => setParams((p) => ({ ...p, min_score: Number(e.target.value) }))}
              />
            </Grid>
            <Grid item xs={12} sm={6} md={2}>
              <TextField
                label="Min ADX"
                type="number"
                fullWidth
                size="small"
                value={params.min_adx ?? ''}
                onChange={(e) => setParams((p) => ({ ...p, min_adx: Number(e.target.value) }))}
              />
            </Grid>
            <Grid item xs={12} sm={6} md={2}>
              <TextField
                label="ATR % min"
                type="number"
                fullWidth
                size="small"
                value={params.atr_pct_min ?? ''}
                onChange={(e) => setParams((p) => ({ ...p, atr_pct_min: Number(e.target.value) }))}
              />
            </Grid>
            <Grid item xs={12} sm={6} md={2}>
              <TextField
                label="ATR % max"
                type="number"
                fullWidth
                size="small"
                value={params.atr_pct_max ?? ''}
                onChange={(e) => setParams((p) => ({ ...p, atr_pct_max: Number(e.target.value) }))}
              />
            </Grid>
            <Grid item xs={12} sm={6} md={2}>
              <TextField
                label="Prox 52W min %"
                type="number"
                fullWidth
                size="small"
                value={params.prox52w_min_pct ?? ''}
                onChange={(e) => setParams((p) => ({ ...p, prox52w_min_pct: Number(e.target.value) }))}
              />
            </Grid>
            <Grid item xs={12} sm={6} md={2}>
              <TextField
                label="Pivot clear min %"
                type="number"
                fullWidth
                size="small"
                value={params.pivot_clear_min_pct ?? ''}
                onChange={(e) => setParams((p) => ({ ...p, pivot_clear_min_pct: Number(e.target.value) }))}
              />
            </Grid>
            <Grid item xs={12} sm={6} md={2}>
              <TextField
                label="Pivot clear max %"
                type="number"
                fullWidth
                size="small"
                value={params.pivot_clear_max_pct ?? ''}
                onChange={(e) => setParams((p) => ({ ...p, pivot_clear_max_pct: Number(e.target.value) }))}
              />
            </Grid>
            <Grid item xs={12} sm={6} md={2}>
              <TextField
                label="Base len min (bars)"
                type="number"
                fullWidth
                size="small"
                value={params.base_len_min_bars ?? ''}
                onChange={(e) => setParams((p) => ({ ...p, base_len_min_bars: Number(e.target.value) }))}
              />
            </Grid>
            <Grid item xs={12} sm={6} md={2}>
              <TextField
                label="RelVol20 min"
                type="number"
                fullWidth
                size="small"
                value={params.relvol20_min ?? ''}
                onChange={(e) => setParams((p) => ({ ...p, relvol20_min: Number(e.target.value) }))}
              />
            </Grid>
            <Grid item xs={12} sm={6} md={2}>
              <TextField
                label="Day change max %"
                type="number"
                fullWidth
                size="small"
                value={params.day_change_max_pct ?? ''}
                onChange={(e) => setParams((p) => ({ ...p, day_change_max_pct: Number(e.target.value) }))}
              />
            </Grid>
            <Grid item xs={12} sm={6} md={2}>
              <TextField
                label="Liquidity min (INR)"
                type="number"
                fullWidth
                size="small"
                value={params.liquidity_min ?? ''}
                onChange={(e) => setParams((p) => ({ ...p, liquidity_min: Number(e.target.value) }))}
              />
            </Grid>
            <Grid item xs={12} sm={6} md={2}>
              <TextField
                label="Stop loss %"
                type="number"
                fullWidth
                size="small"
                value={(params.stop_loss_pct ?? 0) * 100}
                onChange={(e) => setParams((p) => ({ ...p, stop_loss_pct: Number(e.target.value) / 100 }))}
              />
            </Grid>
            <Grid item xs={12} sm={6} md={2}>
              <TextField
                label="Max hold (d)"
                type="number"
                fullWidth
                size="small"
                value={params.max_hold_days ?? ''}
                onChange={(e) => setParams((p) => ({ ...p, max_hold_days: Number(e.target.value) }))}
              />
            </Grid>
            <Grid item xs={12} sm={6} md={2}>
              <TextField
                label="Pool top N"
                type="number"
                fullWidth
                size="small"
                value={params.top_n ?? ''}
                onChange={(e) => setParams((p) => ({ ...p, top_n: Number(e.target.value) }))}
              />
            </Grid>
            <Grid item xs={12} sm={6} md={2}>
              <TextField
                label="Manual symbols (comma separated)"
                fullWidth
                size="small"
                value={manualSymbols}
                onChange={(e) => setManualSymbols(e.target.value)}
              />
            </Grid>
            <Grid item xs={12} sm={6} md={2}>
              <ToggleButtonGroup
                value={params.first_trade_only ? 'first' : 'reentries'}
                exclusive
                size="small"
                onChange={(_e, val) => setParams((p) => ({ ...p, first_trade_only: val === 'first' }))}
              >
                <ToggleButton value="first">First trade only</ToggleButton>
                <ToggleButton value="reentries">Allow re-entries</ToggleButton>
              </ToggleButtonGroup>
            </Grid>
            <Grid item xs={12} sm={6} md={2}>
              <ToggleButtonGroup
                value={autoSweep ? 'auto' : 'manual'}
                exclusive
                size="small"
                onChange={(_e, val) => setAutoSweep(val === 'auto')}
              >
                <ToggleButton value="auto">Auto sweep</ToggleButton>
                <ToggleButton value="manual">Baseline only</ToggleButton>
              </ToggleButtonGroup>
            </Grid>
            <Grid item xs={12} sm={6} md={2} display="flex" alignItems="center" justifyContent="flex-end">
              <Button variant="contained" onClick={handleRun} disabled={loading}>
                {loading ? <CircularProgress size={20} /> : 'Run simulator'}
              </Button>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {error ? <Alert severity="error">{error}</Alert> : null}

      {runs.length > 0 ? (
        <Stack spacing={2}>
          <Card>
            <CardContent>
              <Typography variant="subtitle1" fontWeight={700} sx={{ mb: 1 }}>
                Best 3 combos vs baseline
              </Typography>
              <Divider sx={{ mb: 1.5 }} />
              <Box sx={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                  <thead>
                    <tr style={{ background: 'var(--mui-palette-action-hover)' }}>
                      <th style={{ textAlign: 'left', padding: '10px 10px', borderBottom: '2px solid var(--mui-palette-divider)', minWidth: 140 }}>Parameter</th>
                      {top3.map((r, idx) => (
                        <th
                          key={r.label}
                          style={{
                            textAlign: 'left',
                            padding: '10px 10px',
                            borderBottom: '2px solid var(--mui-palette-divider)',
                            minWidth: 140,
                          }}
                        >
                          <div style={{ fontWeight: 800 }}>{idx === 0 ? 'Baseline' : `Variant ${idx}`}</div>
                          <div style={{ fontSize: 13, fontWeight: 700 }}>{formatPct(r.summary?.avg_return_pct)} avg</div>
                          <div style={{ color: 'var(--mui-palette-text-secondary)' }}>
                            trades {r.summary?.trades ?? 0} · win {formatPct(r.summary?.win_rate_pct)} · total {formatPct(r.summary?.total_return_pct)}
                          </div>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      ['Min score', (p: SimulationParamsPayload) => p.min_score],
                      ['Min ADX', (p) => p.min_adx],
                      ['ATR % min', (p) => p.atr_pct_min],
                      ['ATR % max', (p) => p.atr_pct_max],
                      ['Prox 52W min %', (p) => p.prox52w_min_pct],
                      ['Pivot clear min %', (p) => p.pivot_clear_min_pct],
                      ['Pivot clear max %', (p) => p.pivot_clear_max_pct],
                      ['Base len min (bars)', (p) => p.base_len_min_bars],
                      ['RelVol20 min', (p) => p.relvol20_min],
                      ['Day change max %', (p) => p.day_change_max_pct],
                      ['Liquidity min', (p) => p.liquidity_min],
                  ['Stop loss %', (p) => (p.stop_loss_pct != null ? (p.stop_loss_pct * 100) : p.stop_loss_pct)],
                      ['Max hold (d)', (p) => p.max_hold_days],
                      ['Top N', (p) => p.top_n],
                      ['First trade only', (p) => (p.first_trade_only ? 'Yes' : 'No')],
                    ].map(([label, getter], rowIdx) => (
                      <tr key={label} style={{ borderBottom: '1px dashed var(--mui-palette-divider)', background: rowIdx % 2 ? 'var(--mui-palette-action-hover)' : 'transparent' }}>
                        <td style={{ padding: '10px 10px', fontWeight: 700 }}>{label}</td>
                        {top3.map((r, idx) => {
                          const rawVal = getter(r.params);
                          const rawBase = getter(top3[0].params);
                          const val = typeof rawVal === 'number' ? parseFloat(rawVal.toFixed(2)) : rawVal;
                          const baseVal = typeof rawBase === 'number' ? parseFloat(rawBase.toFixed(2)) : rawBase;
                          const bothNum = typeof val === 'number' && typeof baseVal === 'number' && baseVal !== 0;
                          const deltaPct = bothNum ? (((val as number) - (baseVal as number)) / Math.abs(baseVal as number)) * 100 : null;
                          const changed = idx > 0 && val !== baseVal;
                          const displayVal: string | number = val ?? '--';
                          return (
                            <td
                              key={`${r.label}-${label}`}
                              style={{
                                padding: '10px 10px',
                                color: changed ? 'var(--mui-palette-primary-main)' : 'inherit',
                                fontWeight: changed ? 700 : 500,
                                whiteSpace: 'nowrap',
                              }}
                            >
                              {displayVal}
                              {changed && deltaPct !== null ? (
                                <span style={{ marginLeft: 6, color: deltaPct >= 0 ? 'var(--mui-palette-success-main)' : 'var(--mui-palette-error-main)', fontWeight: 700 }}>
                                  ({deltaPct >= 0 ? '+' : ''}{deltaPct.toFixed(1)}%)
                                </span>
                              ) : null}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Box>
            </CardContent>
          </Card>

          {best ? (
            <Card>
              <CardContent>
                <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
                  <Typography variant="subtitle1" fontWeight={700}>
                    Trades - {best.trades.length} positions
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    Avg return {formatPct(best.summary?.avg_return_pct)} | Win rate {formatPct(best.summary?.win_rate_pct)}
                  </Typography>
                </Stack>
                <Divider sx={{ mb: 1 }} />
                <Grid container spacing={2}>
                  {best.trades.map((t) => (
                    <Grid item xs={12} md={6} lg={4} key={`${t.symbol}-${t.entry_date}`}>
                      <Stack spacing={1} sx={{ p: 1.5, border: '1px solid', borderColor: 'divider', borderRadius: 2 }}>
                        <Stack direction="row" alignItems="center" spacing={1}>
                          <Typography variant="body1" fontWeight={700}>
                            {t.symbol}
                          </Typography>
                          <Chip size="small" color={t.pnl_pct >= 0 ? 'success' : 'error'} label={formatPct(t.pnl_pct)} />
                        </Stack>
                        <Typography variant="caption" color="text.secondary">
                          {`${t.entry_date} -> ${t.exit_date} | ${t.holding_days}d | entry ${t.entry_price.toFixed(2)} exit ${t.exit_price.toFixed(2)}`}
                        </Typography>
                        {best.charts?.[t.symbol] ? <Chart points={best.charts[t.symbol]} trade={t} /> : null}
                      </Stack>
                    </Grid>
                  ))}
                </Grid>
              </CardContent>
            </Card>
          ) : null}
        </Stack>
      ) : (
        <Alert severity="info">Run the simulator to see results. Auto sweep will try three nearby parameter combos.</Alert>
      )}
    </Stack>
  );
}
