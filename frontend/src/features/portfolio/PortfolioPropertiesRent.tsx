import React from 'react';
import { Box, Chip, LinearProgress, Paper, Stack, Typography } from '@mui/material';
import { Bar, BarChart, CartesianGrid, Cell, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

const properties = [
  { name: 'Brigade land', type: 'Land', principal: .82, market: 1.25, monthlyRent: 0, occupancy: 0, color: '#F59E0B' },
  { name: 'Amrapali flat', type: 'Residential', principal: 1.18, market: 1.52, monthlyRent: .0042, occupancy: 92, color: '#2563EB' },
  { name: 'Gera office', type: 'Commercial', principal: .94, market: 1.07, monthlyRent: .0064, occupancy: 100, color: '#7C3AED' },
];

const history = [
  { year: '2023', value: 3.15, rent: .08 }, { year: '2024', value: 3.42, rent: .10 }, { year: '2025', value: 3.68, rent: .12 }, { year: '2026', value: 3.84, rent: .13 },
];
const money = (v: number) => `₹${v.toFixed(2)} Cr`;

const PortfolioPropertiesRent: React.FC = () => {
  const totalMarket = properties.reduce((sum, item) => sum + item.market, 0);
  const annualRent = properties.reduce((sum, item) => sum + item.monthlyRent * 12, 0);
  const yieldPct = annualRent / totalMarket * 100;
  return <Stack spacing={1.5}>
    <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ sm: 'center' }} gap={1}>
      <Box><Typography variant="h6" fontWeight={800}>Properties & rental income</Typography><Typography variant="body2" color="text.secondary">Value creation, income efficiency, and occupancy in one view</Typography></Box>
      <Chip label="UI preview · sample data" size="small" sx={{ bgcolor: '#EEF2FF', color: '#4338CA', fontWeight: 700 }}/>
    </Stack>

    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(3, 1fr)' }, gap: 1.25 }}>
      {properties.map(item => {
        const appreciation = (item.market / item.principal - 1) * 100;
        const rentalYield = item.monthlyRent * 12 / item.market * 100;
        return <Paper key={item.name} variant="outlined" sx={{ p: 1.75, borderRadius: 2.5, borderColor: '#E5EAF1', borderTop: `4px solid ${item.color}` }}>
          <Stack direction="row" justifyContent="space-between"><Box><Typography fontWeight={800}>{item.name}</Typography><Typography variant="caption" color="text.secondary">{item.type}</Typography></Box><Chip label={`${item.occupancy}% occupied`} size="small" color={item.occupancy ? 'success' : 'default'} variant="outlined"/></Stack>
          <Typography sx={{ fontSize: 24, fontWeight: 800, mt: 1 }}>{money(item.market)}</Typography><Typography variant="caption" color="text.secondary">Current market value</Typography>
          <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1, mt: 1.5 }}><Box><Typography variant="caption" color="text.secondary">Principal</Typography><Typography fontWeight={700}>{money(item.principal)}</Typography></Box><Box><Typography variant="caption" color="text.secondary">Appreciation</Typography><Typography fontWeight={700} color="#059669">+{appreciation.toFixed(1)}%</Typography></Box><Box><Typography variant="caption" color="text.secondary">Monthly rent</Typography><Typography fontWeight={700}>{item.monthlyRent ? `₹${Math.round(item.monthlyRent * 10_000_000).toLocaleString('en-IN')}` : 'Not rented'}</Typography></Box><Box><Typography variant="caption" color="text.secondary">Rental yield</Typography><Typography fontWeight={700}>{rentalYield.toFixed(1)}%</Typography></Box></Box>
          <LinearProgress variant="determinate" value={Math.min(rentalYield / 5 * 100, 100)} sx={{ mt: 1.4, height: 6, borderRadius: 4, bgcolor: '#EEF2F6', '& .MuiLinearProgress-bar': { bgcolor: item.color } }}/>
        </Paper>;
      })}
    </Box>

    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: 'minmax(0, 1.35fr) minmax(300px, .65fr)' }, gap: 1.5 }}>
      <Paper variant="outlined" sx={{ p: 2, borderRadius: 2.5, borderColor: '#E5EAF1' }}><Typography fontWeight={800}>Property value and rent growth</Typography><Typography variant="caption" color="text.secondary">Market value and annual rent · ₹ Cr</Typography><Box sx={{ height: 275, mt: 1 }}><ResponsiveContainer width="100%" height="100%"><ComposedChart data={history} margin={{ top: 12, right: 15, left: -10 }}><CartesianGrid stroke="#E9EEF5" vertical={false} strokeDasharray="3 4"/><XAxis dataKey="year" tick={{ fontSize: 11 }}/><YAxis yAxisId="value" tick={{ fontSize: 10 }} tickFormatter={v => `₹${v}`}/><YAxis yAxisId="rent" orientation="right" tick={{ fontSize: 10 }} tickFormatter={v => `₹${v}`}/><Tooltip formatter={(v: number) => money(v)}/><Bar yAxisId="value" dataKey="value" name="Market value" fill="#2563EB" radius={[7, 7, 0, 0]} isAnimationActive={false}/><Line yAxisId="rent" dataKey="rent" name="Annual rent" stroke="#F59E0B" strokeWidth={3} dot={{ r: 4 }} isAnimationActive={false}/></ComposedChart></ResponsiveContainer></Box></Paper>
      <Paper variant="outlined" sx={{ p: 2, borderRadius: 2.5, borderColor: '#E5EAF1' }}><Typography fontWeight={800}>Income efficiency</Typography><Typography variant="caption" color="text.secondary">Gross rental yield by property</Typography><Box sx={{ height: 205, mt: 1 }}><ResponsiveContainer width="100%" height="100%"><BarChart layout="vertical" data={properties.map(item => ({ ...item, yield: item.monthlyRent * 12 / item.market * 100 }))} margin={{ left: 10, right: 20 }}><CartesianGrid stroke="#E9EEF5" horizontal={false}/><XAxis type="number" tickFormatter={v => `${v}%`} tick={{ fontSize: 10 }}/><YAxis type="category" dataKey="name" width={88} tick={{ fontSize: 10 }}/><Tooltip formatter={(v: number) => `${v.toFixed(2)}%`}/><Bar dataKey="yield" radius={[0, 6, 6, 0]} isAnimationActive={false}>{properties.map(item => <Cell key={item.name} fill={item.color}/>)}</Bar></BarChart></ResponsiveContainer></Box><Box sx={{ mt: 1, p: 1.25, bgcolor: '#F0FDF4', borderRadius: 2 }}><Typography variant="caption" color="text.secondary">Portfolio rental yield</Typography><Typography fontSize={22} fontWeight={800} color="#047857">{yieldPct.toFixed(2)}%</Typography><Typography variant="caption">Annual rent {money(annualRent)}</Typography></Box></Paper>
    </Box>
  </Stack>;
};

export default PortfolioPropertiesRent;
