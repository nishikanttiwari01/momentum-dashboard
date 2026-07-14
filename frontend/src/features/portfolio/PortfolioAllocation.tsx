import React from 'react';
import { Box, Stack, Typography } from '@mui/material';
import { Cell, Pie, PieChart, Tooltip } from 'recharts';

export type AllocationItem = { category: string; value: number; weight_pct: number | null };

const COLORS = ['#2e90fa', '#06aed4', '#00b386', '#f79009', '#7a5af8', '#ee46bc', '#98a2b3'];
const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 });
const label = (value: string) => {
  const normalized = value.toLowerCase().replaceAll('_', ' ');
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
};

const PortfolioAllocation: React.FC<{ allocation: AllocationItem[] }> = ({ allocation }) => (
  <Box data-testid="portfolio-allocation-compact" sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '150px minmax(0, 1fr)' }, gap: 1.5, alignItems: 'center' }}>
    <Box aria-label="Allocation by category" role="img" sx={{ height: 154 }}>
        <PieChart width={150} height={154}>
          <Pie data={allocation} dataKey="value" nameKey="category" innerRadius={44} outerRadius={67} paddingAngle={1} stroke="#fff" strokeWidth={2} isAnimationActive={false}>
            {allocation.map((item, index) => <Cell key={item.category} fill={COLORS[index % COLORS.length]} />)}
          </Pie>
          <Tooltip formatter={(value: number) => inr.format(value)} />
        </PieChart>
    </Box>
    <Stack spacing={0.25}>
      {allocation.map((item, index) => (
        <Box key={item.category} sx={{ display: 'grid', gridTemplateColumns: '8px minmax(72px, 1fr) auto', gap: 0.75, alignItems: 'center', py: 0.55, borderBottom: '1px solid', borderColor: 'divider' }}>
          <Box sx={{ width: 8, height: 8, borderRadius: 0.5, bgcolor: COLORS[index % COLORS.length] }} />
          <Typography variant="body2" fontWeight={600}>{label(item.category)}</Typography>
          <Box sx={{ textAlign: 'right' }}>
            <Typography variant="body2" fontWeight={700}>{item.weight_pct == null ? '—' : `${item.weight_pct.toFixed(1)}%`}</Typography>
            <Typography variant="caption" color="text.secondary">{inr.format(item.value)}</Typography>
          </Box>
        </Box>
      ))}
    </Stack>
  </Box>
);

export default PortfolioAllocation;
