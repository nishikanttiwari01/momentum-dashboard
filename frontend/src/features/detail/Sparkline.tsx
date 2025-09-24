// frontend/src/features/detail/Sparkline.tsx
import * as React from 'react';
import { Box, Typography } from '@mui/material';

/** Keep this local so it works even if your API types aren't imported here */
export type DrawerSparkline = {
  prices_30d?: number[];
  ema10_30d?: number[];
};

type Props = {
  data?: DrawerSparkline;  // <- pass d?.sparkline from RightDrawer
  height?: number;         // px height of the SVG area
  showHeader?: boolean;    // show small "30-day trend" header + % change
};

function SparklineBase({ data, height = 84, showHeader = true }: Props) {
  const prices = data?.prices_30d ?? [];
  const ema = data?.ema10_30d ?? [];

  if (!prices.length) {
    return (
      <Box
        sx={{
          height,
          bgcolor: 'action.hover',
          borderRadius: 1,
          mb: 2,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 12,
          color: 'text.secondary',
        }}
      >
        No sparkline
      </Box>
    );
  }

  // Internal SVG canvas (scales to container via width="100%")
  const w = 320;
  const h = height;
  const padX = 4;
  const padY = 4;

  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const span = max - min || 1;

  const n = prices.length;
  const stepX = n > 1 ? (w - padX * 2) / (n - 1) : 0;

  const x = (i: number) => padX + i * stepX;
  const y = (v: number) => h - ((v - min) / span) * (h - padY * 2) - padY;

  const pricePath = prices.map((p, i) => `${i ? 'L' : 'M'} ${x(i)} ${y(p)}`).join(' ');
  const emaPath =
    ema.length === n ? ema.map((p, i) => `${i ? 'L' : 'M'} ${x(i)} ${y(p)}`).join(' ') : null;

  const fillPath = `${pricePath} L ${x(n - 1)} ${h - padY} L ${x(0)} ${h - padY} Z`;

  const pct =
    n >= 2 && prices[0] !== 0 ? ((prices[n - 1] - prices[0]) / prices[0]) * 100 : 0;

  return (
    <Box sx={{ mb: 2 }}>
      {showHeader && (
        <Box sx={{ display: 'flex', alignItems: 'baseline', mb: 0.5, gap: 1 }}>
          <Typography variant="subtitle2" color="text.secondary">
            30-day trend
          </Typography>
          <Typography
            variant="caption"
            sx={{ color: pct >= 0 ? 'success.main' : 'error.main', opacity: 0.9 }}
          >
            {pct >= 0 ? '▲' : '▼'} {pct.toFixed(1)}%
          </Typography>
        </Box>
      )}

      <Box sx={{ height }}>
        <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={h} role="img" aria-label="30-day sparkline">
          {/* soft area fill */}
          <path d={fillPath} fill="currentColor" opacity="0.08" />
          {/* main price line */}
          <path d={pricePath} fill="none" stroke="currentColor" strokeWidth="2" />
          {/* ema(10) overlay */}
          {emaPath && (
            <path d={emaPath} fill="none" stroke="currentColor" strokeWidth="1.25" opacity="0.45" />
          )}
        </svg>
      </Box>
    </Box>
  );
}

export default React.memo(SparklineBase);
