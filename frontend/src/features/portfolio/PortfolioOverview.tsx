import React from 'react';
import { Box, Chip, Paper, Stack, Typography } from '@mui/material';
import { Area, AreaChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

const allocation = [
  { name: 'Mutual funds', value: 3.16, color: '#2563EB' },
  { name: 'Indian stocks', value: 1.48, color: '#06B6D4' },
  { name: 'US holdings', value: 0.54, color: '#7C3AED' },
  { name: 'Property', value: 3.84, color: '#F59E0B' },
  { name: 'Debt & cash', value: 0.42, color: '#10B981' },
];

const wealthHistory = [
  { year: '2023', invested: 5.1, market: 5.8 },
  { year: '2024', invested: 6.4, market: 7.2 },
  { year: '2025', invested: 7.6, market: 8.8 },
  { year: '2026', invested: 8.1, market: 9.44 },
];

const money = (value: number) => `₹${value.toFixed(2)} Cr`;

const PreviewBadge = () => <Chip label="UI preview · sample data" size="small" sx={{ bgcolor: '#EEF2FF', color: '#4338CA', fontWeight: 700 }} />;

const Metric = ({ label, value, note, color = '#102A43' }: { label: string; value: string; note: string; color?: string }) => (
  <Paper variant="outlined" sx={{ p: 1.6, borderColor: '#E5EAF1', borderRadius: 2.5 }}>
    <Typography variant="caption" color="text.secondary">{label}</Typography>
    <Typography sx={{ mt: .25, fontSize: { xs: 20, md: 24 }, lineHeight: 1.15, fontWeight: 800, color }}>{value}</Typography>
    <Typography variant="caption" color="text.secondary">{note}</Typography>
  </Paper>
);

const PortfolioOverview: React.FC = () => {
  const total = allocation.reduce((sum, item) => sum + item.value, 0);
  return <Stack spacing={1.5}>
    <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ sm: 'center' }} gap={1}>
      <Box><Typography variant="h6" fontWeight={800}>Household wealth overview</Typography><Typography variant="body2" color="text.secondary">One view across financial assets and property</Typography></Box>
      <PreviewBadge />
    </Stack>

    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr 1fr', lg: 'repeat(4, 1fr)' }, gap: 1.25 }}>
      <Metric label="Net worth · market value" value={money(9.44)} note="Property included" />
      <Metric label="Invested capital" value={money(8.10)} note="Across all markets" />
      <Metric label="Unrealised gain" value={money(1.34)} note="+16.5% on capital" color="#059669" />
      <Metric label="Global exposure" value="India 94% · US 6%" note="₹0.54 Cr held in US" color="#4F46E5" />
    </Box>

    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: 'minmax(0, 1.35fr) minmax(300px, .65fr)' }, gap: 1.5 }}>
      <Paper variant="outlined" sx={{ p: 2, borderRadius: 2.5, borderColor: '#E5EAF1' }}>
        <Typography fontWeight={800}>Wealth growth</Typography><Typography variant="caption" color="text.secondary">Market value versus invested capital · ₹ Cr</Typography>
        <Box sx={{ height: 260, mt: 1 }}><ResponsiveContainer width="100%" height="100%"><AreaChart data={wealthHistory} margin={{ top: 12, right: 12, left: -18, bottom: 0 }}>
          <defs><linearGradient id="wealthFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#2563EB" stopOpacity={.24}/><stop offset="100%" stopColor="#2563EB" stopOpacity={.02}/></linearGradient></defs>
          <CartesianGrid stroke="#E9EEF5" vertical={false} strokeDasharray="3 4"/><XAxis dataKey="year" tick={{ fontSize: 11 }}/><YAxis tick={{ fontSize: 10 }} tickFormatter={v => `₹${v} Cr`}/><Tooltip formatter={(v: number) => money(v)}/>
          <Area type="monotone" dataKey="market" name="Market value" stroke="#2563EB" strokeWidth={3} fill="url(#wealthFill)" isAnimationActive={false}/><Area type="monotone" dataKey="invested" name="Invested capital" stroke="#94A3B8" strokeWidth={2} fill="transparent" isAnimationActive={false}/>
        </AreaChart></ResponsiveContainer></Box>
      </Paper>

      <Paper variant="outlined" sx={{ p: 2, borderRadius: 2.5, borderColor: '#E5EAF1' }}>
        <Typography fontWeight={800}>Allocation by asset</Typography><Typography variant="caption" color="text.secondary">Current market value</Typography>
        <Box sx={{ height: 165 }}><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={allocation} dataKey="value" innerRadius={48} outerRadius={70} paddingAngle={2} isAnimationActive={false}>{allocation.map(item => <Cell key={item.name} fill={item.color}/>)}</Pie><Tooltip formatter={(v: number) => money(v)}/></PieChart></ResponsiveContainer></Box>
        <Stack spacing={.75}>{allocation.map(item => <Stack key={item.name} direction="row" justifyContent="space-between" alignItems="center"><Stack direction="row" gap={.75} alignItems="center"><Box sx={{ width: 8, height: 8, borderRadius: 2, bgcolor: item.color }}/><Typography variant="body2">{item.name}</Typography></Stack><Typography variant="body2" fontWeight={700}>{Math.round(item.value / total * 100)}% · {money(item.value)}</Typography></Stack>)}</Stack>
      </Paper>
    </Box>

    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(3, 1fr)' }, gap: 1.25 }}>
      {[
        ['Strongest contributor', 'Mutual funds', '₹3.16 Cr across diversified schemes', '#2563EB'],
        ['Concentration watch', 'Property · 41%', 'Review liquidity before major goals', '#F59E0B'],
        ['Next review', 'Increase global mix', 'US allocation is currently 6%', '#7C3AED'],
      ].map(([label, title, note, color]) => <Paper key={label} variant="outlined" sx={{ p: 1.5, borderRadius: 2.5, borderColor: '#E5EAF1', borderTop: `3px solid ${color}` }}><Typography variant="caption" color="text.secondary">{label}</Typography><Typography fontWeight={800}>{title}</Typography><Typography variant="body2" color="text.secondary">{note}</Typography></Paper>)}
    </Box>
  </Stack>;
};

export default PortfolioOverview;
