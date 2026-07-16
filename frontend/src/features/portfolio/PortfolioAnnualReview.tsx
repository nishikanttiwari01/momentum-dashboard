import React from 'react';
import { Box, Chip, MenuItem, Paper, Select, Stack, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material';
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

const reviews = [
  { year: 2024, opening: 5.82, contributions: .62, investmentGain: .52, propertyGrowth: .24, withdrawals: 0, closing: 7.20, xirr: 14.2 },
  { year: 2025, opening: 7.20, contributions: .72, investmentGain: .61, propertyGrowth: .31, withdrawals: -.04, closing: 8.80, xirr: 13.6 },
  { year: 2026, opening: 8.80, contributions: .36, investmentGain: .19, propertyGrowth: .12, withdrawals: -.03, closing: 9.44, xirr: 8.9 },
];

const money = (v: number) => `${v < 0 ? '−' : ''}₹${Math.abs(v).toFixed(2)} Cr`;

const PortfolioAnnualReview: React.FC = () => {
  const [year, setYear] = React.useState(2026);
  const row = reviews.find(item => item.year === year) ?? reviews[0];
  const bridge = [
    { name: 'Opening', value: row.opening, color: '#64748B' },
    { name: 'Contributions', value: row.contributions, color: '#2563EB' },
    { name: 'Investments', value: row.investmentGain, color: '#06B6D4' },
    { name: 'Property', value: row.propertyGrowth, color: '#8B5CF6' },
    { name: 'Withdrawals', value: row.withdrawals, color: '#F97316' },
    { name: 'Closing', value: row.closing, color: '#10B981' },
  ];
  return <Stack spacing={1.5}>
    <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ sm: 'center' }} gap={1}>
      <Box><Typography variant="h6" fontWeight={800}>Annual wealth review</Typography><Typography variant="body2" color="text.secondary">January–December view of cash deployed and wealth created</Typography></Box>
      <Stack direction="row" gap={1}><Chip label="UI preview · sample data" size="small" sx={{ bgcolor: '#EEF2FF', color: '#4338CA', fontWeight: 700 }}/><Select size="small" value={year} onChange={event => setYear(Number(event.target.value))} aria-label="Review year">{reviews.map(item => <MenuItem key={item.year} value={item.year}>{item.year}</MenuItem>)}</Select></Stack>
    </Stack>

    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: 'repeat(2, 1fr)', md: 'repeat(6, 1fr)' }, gap: 1 }}>
      {[
        ['Opening value', money(row.opening), '#102A43'], ['Cash deployed', money(row.contributions), '#2563EB'], ['Investment gains', money(row.investmentGain), '#0891B2'], ['Property growth', money(row.propertyGrowth), '#7C3AED'], ['Closing value', money(row.closing), '#059669'], ['Annual XIRR', `${row.xirr}%`, '#059669'],
      ].map(([label, value, color]) => <Paper key={label} variant="outlined" sx={{ p: 1.35, borderRadius: 2.25, borderColor: '#E5EAF1' }}><Typography variant="caption" color="text.secondary">{label}</Typography><Typography sx={{ color, fontWeight: 800, fontSize: 18 }}>{value}</Typography></Paper>)}
    </Box>

    <Paper variant="outlined" sx={{ p: 2, borderRadius: 2.5, borderColor: '#E5EAF1' }}>
      <Typography fontWeight={800}>{year} wealth bridge</Typography><Typography variant="caption" color="text.secondary">What moved household wealth during the calendar year · ₹ Cr</Typography>
      <Box sx={{ height: 275, mt: 1 }}><ResponsiveContainer width="100%" height="100%"><BarChart data={bridge} margin={{ top: 18, right: 10, left: -10, bottom: 0 }}><CartesianGrid stroke="#E9EEF5" vertical={false} strokeDasharray="3 4"/><XAxis dataKey="name" tick={{ fontSize: 11 }}/><YAxis tick={{ fontSize: 10 }} tickFormatter={v => `₹${v}`}/><Tooltip formatter={(v: number) => money(v)}/><Bar dataKey="value" radius={[7, 7, 0, 0]} isAnimationActive={false}>{bridge.map(item => <Cell key={item.name} fill={item.color}/>)}</Bar></BarChart></ResponsiveContainer></Box>
    </Paper>

    <Paper variant="outlined" sx={{ borderRadius: 2.5, borderColor: '#E5EAF1', overflow: 'hidden' }}>
      <Box sx={{ p: 1.5 }}><Typography fontWeight={800}>Year-by-year scorecard</Typography><Typography variant="caption" color="text.secondary">Compare deployment efficiency and returns</Typography></Box>
      <Box sx={{ overflowX: 'auto' }}><Table size="small"><TableHead><TableRow sx={{ bgcolor: '#F8FAFC' }}>{['Year', 'Opening', 'Contributions', 'Investment gain', 'Property growth', 'Closing', 'XIRR'].map(label => <TableCell key={label} align={label === 'Year' ? 'left' : 'right'} sx={{ fontWeight: 700 }}>{label}</TableCell>)}</TableRow></TableHead><TableBody>{[...reviews].reverse().map(item => <TableRow key={item.year} selected={item.year === year} hover onClick={() => setYear(item.year)} sx={{ cursor: 'pointer' }}><TableCell fontWeight={700}>{item.year}</TableCell>{[item.opening, item.contributions, item.investmentGain, item.propertyGrowth, item.closing].map((value, index) => <TableCell key={index} align="right">{money(value)}</TableCell>)}<TableCell align="right" sx={{ color: '#059669', fontWeight: 800 }}>{item.xirr}%</TableCell></TableRow>)}</TableBody></Table></Box>
    </Paper>
  </Stack>;
};

export default PortfolioAnnualReview;
