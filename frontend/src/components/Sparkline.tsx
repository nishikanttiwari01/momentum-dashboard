import * as React from 'react';
import { Box, Typography, useTheme } from '@mui/material';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Area,
} from 'recharts';

export type DrawerSparkline =
  | {
      // preferred keys from backend
      prices_30d?: (number | string)[];
      ema10_30d?: (number | string)[];
      dates_30d?: (string | number | Date)[];
      // tolerate legacy keys
      prices?: (number | string)[];
      ema10?: (number | string)[];
      dates?: (string | number | Date)[];
    }
  | undefined;

type Props = {
  data?: DrawerSparkline;
  height?: number;        // chart height
  showHeader?: boolean;   // title + % change
};

function toNums(xs?: (number | string)[] | null): number[] {
  if (!Array.isArray(xs)) return [];
  return xs.map(v => (typeof v === 'string' ? Number(v) : v)).filter(Number.isFinite) as number[];
}
function toDates(xs?: (string | number | Date)[] | null): (Date | null)[] {
  if (!Array.isArray(xs)) return [];
  return xs.map(v => {
    const d = v instanceof Date ? v : new Date(v as any);
    return isNaN(d.getTime()) ? null : d;
  });
}
function fmtDate(d: Date | null): string {
  if (!d) return '';
  return new Intl.DateTimeFormat(undefined, { year: 'numeric', month: 'short', day: '2-digit' }).format(d);
}

export default function Sparkline({ data, height = 220, showHeader = true }: Props) {
  const theme = useTheme();

  // accept either ..._30d or legacy keys
  const prices = toNums((data as any)?.prices_30d) || toNums((data as any)?.prices);
  const ema    = toNums((data as any)?.ema10_30d) || toNums((data as any)?.ema10);
  const dates  = toDates((data as any)?.dates_30d) || toDates((data as any)?.dates);

  if (!prices.length) {
    return (
      <Box
        sx={{
          height,
          bgcolor: 'action.hover',
          borderRadius: 2,
          mb: 2,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          px: 1.5,
          fontSize: 12,
          color: 'text.secondary',
          border: t => `1px dashed ${t.palette.divider}`,
        }}
      >
        <span>No chart</span>
        <span>(0 pts)</span>
      </Box>
    );
  }

  const n = prices.length;
  const pct = n >= 2 && prices[0] !== 0 ? ((prices[n - 1] - prices[0]) / prices[0]) * 100 : 0;

  // Build chart rows (one per day)
  const rows = prices.map((p, i) => ({
    idx: i,
    date: dates[i] ?? null,
    label: fmtDate(dates[i] ?? null) || `Day ${i + 1}/${n}`,
    price: p,
    ema: Number.isFinite(ema[i]) ? ema[i] : undefined,
  }));

  // Theme-aware colors
  const priceStroke   = theme.palette.mode === 'dark' ? theme.palette.info.light : theme.palette.info.main;
  const emaStroke     = theme.palette.mode === 'dark' ? theme.palette.success.light : theme.palette.success.main;
  const gridColor     = theme.palette.divider;
  const areaTop       = theme.palette.mode === 'dark' ? 'rgba(56,189,248,0.20)' : 'rgba(56,189,248,0.18)'; // soft cyan
  const areaBottom    = theme.palette.mode === 'dark' ? 'rgba(56,189,248,0.02)' : 'rgba(0,0,0,0.00)';

  return (
    <Box sx={{ mb: 2 }}>
      {showHeader && (
        <Box sx={{ display: 'flex', alignItems: 'baseline', mb: 1, gap: 1 }}>
          <Typography variant="subtitle1" color="text.secondary">
            30-day price
          </Typography>
          <Typography
            variant="caption"
            sx={{ color: pct >= 0 ? 'success.main' : 'error.main', fontWeight: 600 }}
          >
            {pct >= 0 ? '▲' : '▼'} {pct.toFixed(1)}%
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ ml: 'auto' }}>
            ({n} pts)
          </Typography>
        </Box>
      )}

      <Box sx={{ height, bgcolor: 'background.paper', borderRadius: 2, px: 1, pt: 1 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 8, right: 16, left: 8, bottom: 24 }}>
            <defs>
              <linearGradient id="priceArea" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={areaTop} />
                <stop offset="100%" stopColor={areaBottom} />
              </linearGradient>
            </defs>

            <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />

            {/* X axis: use human labels if dates present; else compact day labels */}
            <XAxis
              dataKey="label"
              tick={{ fontSize: 11, fill: theme.palette.text.secondary }}
              tickLine={false}
              axisLine={false}
              minTickGap={24}
              interval="preserveStartEnd"
            />

            {/* Y axis: prices */}
            <YAxis
              tick={{ fontSize: 11, fill: theme.palette.text.secondary }}
              tickFormatter={(v) => Number(v).toFixed(0)}
              tickLine={false}
              axisLine={false}
              width={38}
              domain={['dataMin', 'dataMax']}
            />

            {/* Soft area under the price */}
            <Area
              type="monotone"
              dataKey="price"
              stroke="none"
              fill="url(#priceArea)"
              isAnimationActive={false}
            />

            {/* Price line */}
            <Line
              type="monotone"
              dataKey="price"
              stroke={priceStroke}
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />

            {/* EMA(10) overlay if available */}
            <Line
              type="monotone"
              dataKey="ema"
              stroke={emaStroke}
              strokeWidth={1.6}
              dot={false}
              isAnimationActive={false}
              connectNulls
            />

            <Tooltip
              cursor={{ stroke: gridColor, strokeWidth: 1 }}
              contentStyle={{
                background: theme.palette.background.paper,
                border: `1px solid ${gridColor}`,
                borderRadius: 8,
                padding: '6px 8px',
              }}
              formatter={(value: any, key: any) => {
                if (key === 'price') return [Number(value).toFixed(2), 'Close'];
                if (key === 'ema')   return [Number(value).toFixed(2), 'EMA10'];
                return [value, key];
              }}
              labelFormatter={(_, payload) => {
                const p = payload && payload[0] && (payload[0].payload as any);
                return p?.label ?? '';
              }}
            />
          </LineChart>
        </ResponsiveContainer>
      </Box>
    </Box>
  );
}
