import * as React from 'react';
import axios from 'axios';
import dayjs from 'dayjs';
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
  LinearProgress,
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
  take_profit_pct?: number;
  max_hold_days?: number | null;
  top_n?: number | null;
  first_trade_only?: boolean;
  recommendation_only?: boolean;
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

type SimulationMeta = {
  min_runs?: number;
  max_runs?: number;
  seed?: number;
  target_total_return_pct?: number;
  runs_evaluated?: number;
  best_total_return_pct?: number;
  target_met?: boolean;
  planned_total_runs?: number;
  stopped_early?: boolean;
};

type SimulationResponse = { runs: SimulationRun[]; meta?: SimulationMeta | null };

type SimulationJobStart = { job_id: string };
type SimulationJobStatus = {
  job_id: string;
  status: 'running' | 'done' | 'error';
  progress: { completed: number; total: number; label?: string | null };
  meta?: SimulationMeta | null;
  error?: string | null;
};

const formatPct = (v?: number) => (v == null ? '--' : `${v.toFixed(2)}%`);

const defaultStart = () => dayjs().subtract(1, 'month').startOf('month').format('YYYY-MM-DD');
const defaultEnd = () => dayjs().subtract(1, 'month').endOf('month').format('YYYY-MM-DD');

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
    take_profit_pct: 0.1,
    max_hold_days: null,
    top_n: 3,
    first_trade_only: true,
    recommendation_only: true,
  });
  const [manualSymbols, setManualSymbols] = React.useState('');
  const [autoSweep, setAutoSweep] = React.useState(true);
  const [runs, setRuns] = React.useState<SimulationRun[]>([]);
  const [meta, setMeta] = React.useState<SimulationMeta | null>(null);
  const [jobId, setJobId] = React.useState<string | null>(null);
  const [jobStatus, setJobStatus] = React.useState<SimulationJobStatus | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const buildSweep = React.useCallback(() => {
    if (!autoSweep) return undefined;
    const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));
    const around = (v: number, step: number, lo: number, hi: number) => {
      const vals = [v - step, v, v + step].map((x) => clamp(x, lo, hi));
      return Array.from(new Set(vals.map((x) => Number(x.toFixed(4)))));
    };
    const aroundInt = (v: number, step: number, lo: number, hi: number) => {
      const vals = [v - step, v, v + step].map((x) => Math.round(clamp(x, lo, hi)));
      return Array.from(new Set(vals));
    };

    return {
      enabled: true,
      min_runs: 20,
      max_runs: 500,
      seed: 42,
      target_total_return_pct: 10,
      prefer_profitable: true,
      ranges: {
        min_score: around(params.min_score ?? 70, 4, 40, 95),
        min_adx: around(params.min_adx ?? 22, 4, 10, 45),
        atr_pct_min: around(params.atr_pct_min ?? 2, 1, 0, 20),
        atr_pct_max: around(params.atr_pct_max ?? 8, 1, 2, 25),
        prox52w_min_pct: around(params.prox52w_min_pct ?? -8, 4, -35, 10),
        pivot_clear_min_pct: around(params.pivot_clear_min_pct ?? -0.3, 0.5, -5, 10),
        pivot_clear_max_pct: around(params.pivot_clear_max_pct ?? 6, 1, 0, 20),
        base_len_min_bars: aroundInt(params.base_len_min_bars ?? 5, 2, 3, 20),
        relvol20_min: around(params.relvol20_min ?? 1.3, 0.2, 0.5, 3),
        day_change_max_pct: around(params.day_change_max_pct ?? 6, 2, 1, 20),
        liquidity_min: [
          Math.max(1, (params.liquidity_min ?? 50_000_000) * 0.7),
          params.liquidity_min ?? 50_000_000,
          (params.liquidity_min ?? 50_000_000) * 1.3,
        ],
        top_n: [1, 3, 5],
      },
    };
  }, [autoSweep, params]);

  const handleRun = async () => {
    setLoading(true);
    setError(null);
    setRuns([]);
    setMeta(null);
    setJobStatus(null);
    try {
      const manual = manualSymbols
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
      const body = {
        start_date: startDate,
        end_date: endDate,
        params,
        sweep: buildSweep(),
        manual_symbols: manual.length ? manual : undefined,
      };
      const resp = await axios.post<SimulationJobStart>('/api/v1/simulator/run_async', body);
      setJobId(resp.data.job_id);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || 'Failed to run simulator');
      setLoading(false);
    } finally {
      // loading will be cleared when job completes
    }
  };

  React.useEffect(() => {
    if (!jobId) return;
    let cancelled = false;

    const poll = async () => {
      try {
        const resp = await axios.get<SimulationJobStatus>(`/api/v1/simulator/status/${jobId}`);
        if (cancelled) return;
        setJobStatus(resp.data);
        if (resp.data.status === 'done') {
          const result = await axios.get<SimulationResponse>(`/api/v1/simulator/result/${jobId}`);
          if (cancelled) return;
          setRuns(result.data.runs || []);
          setMeta(result.data.meta || null);
          setLoading(false);
          setJobId(null);
        } else if (resp.data.status === 'error') {
          setError(resp.data.error || 'Simulator failed');
          setLoading(false);
          setJobId(null);
        }
      } catch (err: any) {
        if (cancelled) return;
        setError(err?.response?.data?.detail || err?.message || 'Failed to fetch simulator status');
        setLoading(false);
        setJobId(null);
      }
    };

    poll();
    const timer = setInterval(poll, 1500);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [jobId]);

  const baseline = React.useMemo(() => runs.find((r) => r.label === 'baseline') || null, [runs]);
  const ranked = React.useMemo(() => runs.filter((r) => r.label !== 'baseline'), [runs]);
  const best = ranked[0] || baseline || null;
  const top3 = ranked.slice(0, 3);
  const tableRuns = React.useMemo(() => {
    const cols: SimulationRun[] = [];
    if (baseline) cols.push(baseline);
    cols.push(...top3);
    return cols.length ? cols : runs;
  }, [baseline, top3, runs]);
  const baseRun = baseline || tableRuns[0] || null;
  const recommendationRows = React.useMemo(() => {
    if (!baseline || !best || baseline === best) return [];
    const fields: Array<[string, (p: SimulationParamsPayload) => number | string | null | undefined]> = [
      ['Min score', (p) => p.min_score],
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
      ['Stop loss %', (p) => (p.stop_loss_pct != null ? p.stop_loss_pct * 100 : p.stop_loss_pct)],
      ['Take profit %', (p) => (p.take_profit_pct != null ? p.take_profit_pct * 100 : p.take_profit_pct)],
      ['Max hold (d)', (p) => p.max_hold_days],
      ['Top N', (p) => p.top_n],
      ['First trade only', (p) => (p.first_trade_only ? 'Yes' : 'No')],
    ];
    return fields
      .map(([label, getter]) => {
        const baseVal = getter(baseline.params);
        const bestVal = getter(best.params);
        const changed = baseVal !== bestVal;
        return { label, baseVal, bestVal, changed };
      })
      .filter((r) => r.changed);
  }, [baseline, best]);

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
                label="Take profit %"
                type="number"
                fullWidth
                size="small"
                value={(params.take_profit_pct ?? 0) * 100}
                onChange={(e) => setParams((p) => ({ ...p, take_profit_pct: Number(e.target.value) / 100 }))}
              />
            </Grid>
            <Grid item xs={12} sm={6} md={2}>
              <TextField
                label="Max hold (d)"
                type="number"
                fullWidth
                size="small"
                value={params.max_hold_days ?? ''}
                onChange={(e) => {
                  const raw = e.target.value;
                  setParams((p) => ({ ...p, max_hold_days: raw === '' ? null : Number(raw) }));
                }}
              />
            </Grid>
            <Grid item xs={12} sm={6} md={2}>
              <TextField
                label="Pool top N"
                type="number"
                fullWidth
                size="small"
                value={params.top_n ?? ''}
                onChange={(e) => {
                  const raw = e.target.value;
                  setParams((p) => ({ ...p, top_n: raw === '' ? null : Number(raw) }));
                }}
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
              <Button variant="contained" onClick={handleRun} disabled={loading || !!jobId}>
                {loading ? <CircularProgress size={20} /> : 'Run simulator'}
              </Button>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {jobStatus?.status === 'running' ? (
        <Card>
          <CardContent>
            <Stack spacing={1}>
              <Typography variant="subtitle2" fontWeight={700}>
                Running sweep…
              </Typography>
              <LinearProgress
                variant={jobStatus.progress?.total ? 'determinate' : 'indeterminate'}
                value={
                  jobStatus.progress?.total
                    ? Math.min(100, (jobStatus.progress.completed / jobStatus.progress.total) * 100)
                    : undefined
                }
              />
              <Typography variant="caption" color="text.secondary">
                Iteration {jobStatus.progress?.completed ?? 0} / {jobStatus.progress?.total ?? 0}
                {jobStatus.progress?.label ? ` · ${jobStatus.progress.label}` : ''}
              </Typography>
            </Stack>
          </CardContent>
        </Card>
      ) : null}

      {error ? <Alert severity="error">{error}</Alert> : null}

      {runs.length > 0 ? (
        <Stack spacing={2}>
          {meta ? (
            <Alert severity={meta.target_met ? 'success' : 'warning'}>
              {meta.target_met
                ? `Target met: best total return ${formatPct(meta.best_total_return_pct)} across ${meta.runs_evaluated ?? runs.length} runs.`
                : `Target not met: best total return ${formatPct(meta.best_total_return_pct)} after ${meta.runs_evaluated ?? runs.length} runs (target ${formatPct(meta.target_total_return_pct)}).`}
            </Alert>
          ) : null}
          <Card>
            <CardContent>
              <Typography variant="subtitle1" fontWeight={700} sx={{ mb: 1 }}>
                Baseline vs Top 3
              </Typography>
              <Divider sx={{ mb: 1.5 }} />
              <Box sx={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                  <thead>
                    <tr style={{ background: 'var(--mui-palette-action-hover)' }}>
                      <th style={{ textAlign: 'left', padding: '10px 10px', borderBottom: '2px solid var(--mui-palette-divider)', minWidth: 140 }}>Parameter</th>
                      {tableRuns.map((r, idx) => (
                        <th
                          key={r.label}
                          style={{
                            textAlign: 'left',
                            padding: '10px 10px',
                            borderBottom: '2px solid var(--mui-palette-divider)',
                            minWidth: 140,
                          }}
                        >
                          <div style={{ fontWeight: 800 }}>
                            {baseline && idx === 0 ? 'Baseline' : `Best ${baseline ? idx : idx + 1}`}
                          </div>
                          <div style={{ fontSize: 11, color: 'var(--mui-palette-text-secondary)' }}>{r.label}</div>
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
                      ['Take profit %', (p) => (p.take_profit_pct != null ? (p.take_profit_pct * 100) : p.take_profit_pct)],
                      ['Max hold (d)', (p) => p.max_hold_days],
                      ['Top N', (p) => p.top_n],
                      ['First trade only', (p) => (p.first_trade_only ? 'Yes' : 'No')],
                    ].map(([label, getter], rowIdx) => (
                      <tr key={label} style={{ borderBottom: '1px dashed var(--mui-palette-divider)', background: rowIdx % 2 ? 'var(--mui-palette-action-hover)' : 'transparent' }}>
                        <td style={{ padding: '10px 10px', fontWeight: 700 }}>{label}</td>
                        {tableRuns.map((r, idx) => {
                          const rawVal = getter(r.params);
                          const rawBase = baseRun ? getter(baseRun.params) : rawVal;
                          const val = typeof rawVal === 'number' ? parseFloat(rawVal.toFixed(2)) : rawVal;
                          const baseVal = typeof rawBase === 'number' ? parseFloat(rawBase.toFixed(2)) : rawBase;
                          const bothNum = typeof val === 'number' && typeof baseVal === 'number' && baseVal !== 0;
                          const deltaPct = bothNum ? (((val as number) - (baseVal as number)) / Math.abs(baseVal as number)) * 100 : null;
                          const changed = baseRun && r.label !== baseRun.label && val !== baseVal;
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

          {baseline && best && recommendationRows.length > 0 ? (
            <Card>
              <CardContent>
                <Typography variant="subtitle1" fontWeight={700} sx={{ mb: 1 }}>
                  Recommended Scoring Adjustments
                </Typography>
                <Divider sx={{ mb: 1.5 }} />
                <Stack spacing={0.5}>
                  {recommendationRows.map((row) => (
                    <Typography key={row.label} variant="body2">
                      {row.label}: {String(row.baseVal ?? '--')} → {String(row.bestVal ?? '--')}
                    </Typography>
                  ))}
                </Stack>
              </CardContent>
            </Card>
          ) : null}

          {best ? (
            <Card>
              <CardContent>
                <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
                  <Typography variant="subtitle1" fontWeight={700}>
                    Trades - {best.trades.length} positions
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    Avg return {formatPct(best.summary?.avg_return_pct)} | Win rate {formatPct(best.summary?.win_rate_pct)} | Total {formatPct(best.summary?.total_return_pct)}
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
        <Alert severity="info">Run the simulator to see results. Auto sweep samples parameter combinations to rank the top 3.</Alert>
      )}
    </Stack>
  );
}


