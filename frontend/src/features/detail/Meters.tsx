// detail/Meters.tsx
import * as React from 'react';
import { Box, Grid, Stack, Tooltip, Typography } from '@mui/material';

type MeterData = {
  score_0_100?: number;
  level?: string;
  basis?: Record<string, number | string>;
};

export default function Meters(props: { risk?: MeterData; euphoria?: MeterData }) {
  const { risk, euphoria } = props;

  return (
    <Grid container spacing={2} columns={12}>
      <Grid item xs={6}>
        <Gauge
          label="Risk"
          score={pickScore(risk?.score_0_100, risk?.level)}
          level={deriveLevel(risk?.score_0_100, risk?.level)}
          gradientStops={[
            { at: 0,   color: '#2e7d32' },
            { at: 0.6, color: '#ed6c02' },
            { at: 1,   color: '#d32f2f' },
          ]}
          basis={risk?.basis}
        />
      </Grid>
      <Grid item xs={6}>
        <Gauge
          label="Euphoria"
          score={pickScore(euphoria?.score_0_100, euphoria?.level)}
          level={deriveLevel(euphoria?.score_0_100, euphoria?.level)}
          gradientStops={[
            { at: 0,   color: '#0288d1' },
            { at: 0.6, color: '#7b1fa2' },
            { at: 1,   color: '#e91e63' },
          ]}
          basis={euphoria?.basis}
        />
      </Grid>
    </Grid>
  );
}

/** ---------------- Gauge (half circle) ---------------- */
const Gauge: React.FC<{
  label: string;
  score?: number; // 0..100
  level: 'Low' | 'Medium' | 'High' | '—';
  gradientStops: { at: number; color: string }[];
  basis?: Record<string, number | string>;
}> = ({ label, score, level, gradientStops, basis }) => {
  const v = typeof score === 'number' ? clamp(score, 0, 100) : undefined;

  // Geometry (drawn in a fixed viewBox, then scaled to 100% width of its grid cell)
  const PAD_X = 18;     // side padding in the viewBox so 0/100 labels never clip
  const PAD_TOP = 6;
  const W = 180;        // narrower base so two fit comfortably in the drawer
  const H = 90;
  const R = 72;
  const CX = PAD_X + W / 2;
  const CY = R + 14 + PAD_TOP;
  const STROKE = 10;

  const fullArcPath = arc(CX, CY, R, 180, 0);

  // Needle
  const angle = typeof v === 'number' ? (180 - (v / 100) * 180) : 180;
  const tip = polar(CX, CY, R - 10, angle);

  // Ticks + numeric labels (0..100 every 20; minor every 10)
  const items: React.ReactNode[] = [];
  for (let t = 0; t <= 100; t += 10) {
    const major = t % 20 === 0;
    const a = 180 - (t / 100) * 180;
    const p1 = polar(CX, CY, R + (major ? 0 : 2), a);
    const p2 = polar(CX, CY, R - (major ? 10 : 6), a);
    items.push(
      <line
        key={`tick-${t}`}
        x1={p1.x} y1={p1.y} x2={p2.x} y2={p2.y}
        stroke="rgba(255,255,255,.28)"
        strokeWidth={major ? 2 : 1}
      />
    );
    if (major) {
      const pt = polar(CX, CY, R + 16, a);
      items.push(
        <text
          key={`lbl-${t}`}
          x={pt.x}
          y={pt.y}
          textAnchor="middle"
          dominantBaseline="middle"
          style={{ fontSize: 11, fill: 'rgba(255,255,255,.55)' }}
        >
          {t}
        </text>
      );
    }
  }

  const gradId = React.useId();
  const tipText = basis && Object.keys(basis).length
    ? Object.entries(basis)
        .map(([k, val]) => `${k}: ${typeof val === 'number' && isFinite(val) ? val.toFixed(2) : String(val)}`)
        .join(' · ')
    : '';
  const needleColor = sampleGradient(gradientStops, (v ?? 0) / 100);

  return (
    <Tooltip title={tipText} disableHoverListener={!tipText}>
      <Stack spacing={0.5} alignItems="center" sx={{ width: '100%' }}>
        {/* SVG scales to 100% width of its grid cell; fixed height keeps proportions tidy */}
        <Box
          component="svg"
          viewBox={`0 0 ${W + PAD_X * 2} ${H + PAD_TOP}`}
          sx={{ width: '100%', height: H, overflow: 'visible' }}
        >
          <defs>
            <linearGradient id={gradId} x1="0%" y1="0%" x2="100%" y2="0%">
              {gradientStops.map((s, i) => (
                <stop key={i} offset={`${s.at * 100}%`} stopColor={s.color} />
              ))}
            </linearGradient>
          </defs>

          {/* full gradient arc */}
          <path
            d={fullArcPath}
            stroke={`url(#${gradId})`}
            strokeWidth={STROKE}
            strokeLinecap="round"
            fill="none"
            opacity={0.95}
          />

          {/* ticks + labels */}
          {items}

          {/* needle */}
          {typeof v === 'number' && (
            <>
              <line x1={CX} y1={CY} x2={tip.x} y2={tip.y} stroke={needleColor} strokeWidth={3} />
              <circle cx={CX} cy={CY} r={4} fill={needleColor} />
            </>
          )}
        </Box>

        {/* single tight label row under the dial */}
        <Stack direction="row" spacing={0.75} alignItems="baseline" sx={{ mt: -0.25 }}>
          <Typography variant="body2" sx={{ color: 'text.secondary' }}>
            {label}:
          </Typography>
          <Typography variant="body2" sx={{ fontWeight: 700 }}>
            {level}
          </Typography>
        </Stack>
      </Stack>
    </Tooltip>
  );
};

/** ---------------- helpers ---------------- */
function clamp(x: number, a: number, b: number) { return Math.max(a, Math.min(b, x)); }
function polar(cx: number, cy: number, r: number, angleDeg: number) {
  const rad = (Math.PI / 180) * angleDeg;
  return { x: cx + r * Math.cos(rad), y: cy - r * Math.sin(rad) };
}
// Replace the existing arc() helper with this one
function arc(cx: number, cy: number, r: number, startDeg: number, endDeg: number) {
  const start = polar(cx, cy, r, startDeg);
  const end = polar(cx, cy, r, endDeg); // <-- use cx, cy (NOT CX, CY)
  const largeArcFlag = Math.abs(endDeg - startDeg) > 180 ? 1 : 0;
  const sweepFlag = endDeg < startDeg ? 1 : 0;
  return `M ${start.x} ${start.y} A ${r} ${r} 0 ${largeArcFlag} ${sweepFlag} ${end.x} ${end.y}`;
}

function pickScore(score?: number, level?: string) {
  if (typeof score === 'number' && isFinite(score)) return score;
  switch (String(level || '').toLowerCase()) {
    case 'low': return 25;
    case 'medium': return 60;
    case 'high': return 85;
    default: return undefined;
  }
}
function deriveLevel(score?: number, level?: string): 'Low' | 'Medium' | 'High' | '—' {
  if (typeof level === 'string' && level) {
    const l = level.toLowerCase();
    if (l.startsWith('low')) return 'Low';
    if (l.startsWith('med')) return 'Medium';
    if (l.startsWith('high')) return 'High';
  }
  if (typeof score === 'number') {
    if (score < 34) return 'Low';
    if (score < 67) return 'Medium';
    return 'High';
  }
  return '—';
}
function sampleGradient(stops: { at: number; color: string }[], t: number) {
  if (!stops.length) return '#999';
  if (t <= stops[0].at) return stops[0].color;
  for (let i = 1; i < stops.length; i++) {
    const a = stops[i - 1], b = stops[i];
    if (t <= b.at) return lerpColor(a.color, b.color, (t - a.at) / (b.at - a.at));
  }
  return stops[stops.length - 1].color;
}
function lerpColor(a: string, b: string, t: number) {
  const pa = hexToRgb(a), pb = hexToRgb(b);
  const r = Math.round(pa.r + (pb.r - pa.r) * t);
  const g = Math.round(pa.g + (pb.g - pa.g) * t);
  const bl = Math.round(pa.b + (pb.b - pa.b) * t);
  return `rgb(${r}, ${g}, ${bl})`;
}
function hexToRgb(hex: string) {
  const h = hex.replace('#', '');
  const full = h.length === 3 ? h.split('').map(c => c + c).join('') : h;
  const n = parseInt(full, 16);
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}
