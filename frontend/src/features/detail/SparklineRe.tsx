// frontend/src/features/detail/SparklineRe.tsx
import * as React from 'react';
import { Box, Typography, useTheme } from '@mui/material';
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, Area,
} from 'recharts';

export type DrawerSparkline =
  | {
      prices_30d?: (number | string)[];
      ema10_30d?: (number | string)[];
      dates_30d?: (string | number | Date)[];
      // tolerate legacy keys too
      prices?: (number | string)[];
      ema10?: (number | string)[];
      dates?: (string | number | Date)[];
    }
  | undefined;

type Props = { data?: DrawerSparkline; height?: number; showHeader?: boolean };

const toNums = (xs?: (number | string)[] | null): number[] =>
  Array.isArray(xs) ? (xs.map(v => (typeof v === 'string' ? Number(v) : v)).filter(Number.isFinite) as number[]) : [];

const toDates = (xs?: (string | number | Date)[] | null): (Date | null)[] =>
  Array.isArray(xs)
    ? xs.map(v => {
        const d = v instanceof Date ? v : new Date(v as any);
        return isNaN(d.getTime()) ? null : d;
      })
    : [];

const fmtDate = (d: Date | null): string =>
  d ? new Intl.DateTimeFormat(undefined, { year: 'numeric', month: 'short', day: '2-digit' }).format(d) : '';

export default function SparklineRe({ data, height = 220, showHeader = true }: Props) {
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

  // Build rows. Add separate key 'priceFill' for the Area so it won't duplicate in tooltip.
  const rows = prices.map((p, i) => ({
    idx: i,
    date: dates[i] ?? null,
    label: fmtDate(dates[i] ?? null) || `Day ${i + 1}/${n}`,
    price: p,
    priceFill: p, // <- used only for gradient area
    ema: Number.isFinite(ema[i]) ? ema[i] : undefined,
  }));

  // Custom tooltip that hides 'priceFill' and dedupes Close
  const CustomTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload || !payload.length) return null;

    const items: Array<{ name: string; value: number, color?: string }> = [];
    let addedClose = false;

    for (const it of payload) {
      const key = it.dataKey;
      if (key === 'priceFill') continue;          // hide area values
      if (key === 'price') {
        if (addedClose) continue;                 // dedupe Close
        addedClose = true;
        items.push({ name: 'Close', value: Number(it.value), color: priceStroke });
        continue;
      }
      if (key === 'ema') items.push({ name: 'EMA10', value: Number(it.value), color: emaStroke });
    }

    return (
      <div
        style={{
          background: `${getComputedStyle(document.documentElement).getPropertyValue('--tooltip-bg') || ''}` || 'var(--mui-palette-background-paper,#fff)',
          border: '1px solid rgba(128,128,128,0.3)',
          borderRadius: 8,
          padding: '6px 8px',
          fontSize: 11,
        }}
      >
        <div style={{ marginBottom: 4, opacity: 0.8 }}>{label}</div>
        {items.map((it, i) => (
          <div key={i} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, color: it.color }}>
            <span>{it.name}</span>
            <span>{it.value.toFixed(2)}</span>
          </div>
        ))}
      </div>
    );
  };

  // Theme-aware colors
  const priceStroke = theme.palette.info.main;
  const emaStroke   = theme.palette.success.dark;
  const gridColor   = theme.palette.divider;
  const areaTop     = theme.palette.mode === 'dark' ? 'rgba(56,189,248,0.20)' : 'rgba(56,189,248,0.18)';
  const areaBottom  = theme.palette.mode === 'dark' ? 'rgba(56,189,248,0.02)' : 'rgba(0,0,0,0.00)';

  return (
    <Box sx={{ mb: 2 }}>
      {showHeader && (
        <Box sx={{ display: 'flex', alignItems: 'baseline', mb: 1, gap: 1 }}>
          <Typography variant="subtitle1" color="text.secondary">
            30-day price
          </Typography>
          <Typography variant="caption" sx={{ color: pct >= 0 ? 'success.main' : 'error.main', fontWeight: 600 }}>
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

            {/* Real dates if provided, else Day i/N labels */}
            <XAxis
              dataKey="label"
              tick={{ fontSize: 11, fill: theme.palette.text.secondary }}
              tickLine={false}
              axisLine={false}
              minTickGap={24}
              interval="preserveStartEnd"
            />
            <YAxis
              tick={{ fontSize: 11, fill: theme.palette.text.secondary }}
              tickFormatter={(v) => Number(v).toFixed(0)}
              tickLine={false}
              axisLine={false}
              width={38}
              domain={['dataMin', 'dataMax']}
            />

            {/* Area uses separate key so it won't duplicate in tooltip */}
            <Area type="monotone" dataKey="priceFill" stroke="none" fill="url(#priceArea)" isAnimationActive={false} />

            {/* Main price line */}
          <Line type="monotone" dataKey="price" stroke={priceStroke} strokeWidth={1.5} dot={false} isAnimationActive={false} />

          {/* EMA overlay if available */}
          <Line type="monotone" dataKey="ema" stroke={emaStroke} strokeWidth={1.2} dot={false} isAnimationActive={false} connectNulls />

            <Tooltip
              cursor={{ stroke: gridColor, strokeWidth: 1 }}
              content={<CustomTooltip />}
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
