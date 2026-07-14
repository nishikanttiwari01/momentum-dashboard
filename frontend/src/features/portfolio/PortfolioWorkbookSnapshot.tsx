import React from 'react';
import { Box, Paper, Stack, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material';
import AutoGraphRoundedIcon from '@mui/icons-material/AutoGraphRounded';
import BalanceRoundedIcon from '@mui/icons-material/BalanceRounded';
import DonutLargeRoundedIcon from '@mui/icons-material/DonutLargeRounded';
import { Area, AreaChart, Bar, BarChart, CartesianGrid, LabelList, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { PortfolioSectionHeader, assetIconFor } from './PortfolioVisuals';

const history = [
  { year: 'FY-24', principal: 4.92, market: 5.82, savings: 0.51, profit: 2.4 },
  { year: 'FY-25', principal: 5.76, market: 8.25, savings: 0.84, profit: 10.6 },
  { year: 'FY-26', principal: 5.87, market: 8.31, savings: 0.11, profit: 9.1 },
];

const currentAssets = [
  { name: 'Mutual funds', detail: 'Live values shown in the fund table below', principal: '₹2.64 Cr', market: '₹3.16 Cr', gain: '+19.7%' },
  { name: 'Stocks', detail: 'Direct equity holdings', principal: '₹21.0 L', market: '₹25.2 L', gain: '+20.0%' },
  { name: 'Debt + savings', detail: 'Deposits, liquid funds and savings', principal: '₹1.45 Cr', market: '₹1.45 Cr', gain: '—' },
];

const fixedAssets = [
  { name: 'Brigade land', type: 'Residential land', principal: '₹99.59 L', market: '₹2.16 Cr' },
  { name: 'Amrapali flat', type: 'Residential flat', principal: '₹20.50 L', market: '₹68.00 L' },
  { name: 'Gera office', type: 'Office', principal: '₹57.00 L', market: '₹1.00 Cr' },
];

const croreLabel = (value: number) => `₹${value.toFixed(2)} Cr`;

export const PortfolioWealthGrowth: React.FC = () => (
    <Paper data-testid="portfolio-wealth-growth" variant="outlined" sx={{ p: 2.25, height: '100%', boxSizing: 'border-box', borderRadius: 3, borderColor: '#E4EAF3', boxShadow: '0 10px 28px rgba(20,33,61,0.055)' }}>
      <PortfolioSectionHeader icon={<AutoGraphRoundedIcon fontSize="small" />} title="Wealth growth over years" detail="Market value compared with principal · ₹ Cr" />
      <Stack direction="row" spacing={1} sx={{ mb: 0.5, flexWrap: 'wrap' }}>
        {history.map((item) => <Box key={item.year} sx={{ px: 1, py: 0.35, borderRadius: 1.5, bgcolor: '#EFF6FF', color: '#175CD3', fontSize: 11, fontWeight: 800 }}>{item.year} · {croreLabel(item.market)}</Box>)}
      </Stack>
      <Box data-chart-type="wealth-area" sx={{ height: 210 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={history} margin={{ top: 28, right: 30, left: 0, bottom: 0 }}>
            <defs><linearGradient id="wealthMarketFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#2E7CF6" stopOpacity={0.34} /><stop offset="100%" stopColor="#12B76A" stopOpacity={0.04} /></linearGradient></defs>
            <CartesianGrid stroke="#E9EEF5" vertical={false} strokeDasharray="3 4" />
            <XAxis dataKey="year" tick={{ fontSize: 11 }} />
            <YAxis domain={[4, 9]} tick={{ fontSize: 11 }} tickFormatter={(value) => `₹${value} Cr`} width={58} />
            <Tooltip formatter={(value: number, name: string) => [croreLabel(value), name]} contentStyle={{ borderRadius: 10, borderColor: '#E4E7EC', boxShadow: '0 8px 24px rgba(20,33,61,.12)' }} />
            <Legend />
            <Area type="monotone" dataKey="market" name="Market value" stroke="#2E7CF6" strokeWidth={3} fill="url(#wealthMarketFill)" activeDot={{ r: 6 }} isAnimationActive={false}><LabelList dataKey="market" position="top" formatter={(value: number) => croreLabel(value)} style={{ fill: '#175CD3', fontSize: 11, fontWeight: 800 }} /></Area>
            <Line type="monotone" dataKey="principal" name="Principal" stroke="#98A2B3" strokeWidth={2} strokeDasharray="6 5" dot={{ r: 3 }} isAnimationActive={false} />
          </AreaChart>
        </ResponsiveContainer>
      </Box>
      <Stack direction="row" justifyContent="flex-end"><Typography variant="caption" color="text.secondary">Latest market value <b style={{ color: '#175CD3' }}>₹8.31 Cr</b></Typography></Stack>
    </Paper>
);

export const PortfolioAssetPanels: React.FC = () => (
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: '1.2fr 1fr' }, gap: 2 }}>
      <Paper variant="outlined" sx={{ p: 2, overflowX: 'auto' }}>
        <PortfolioSectionHeader icon={<DonutLargeRoundedIcon fontSize="small" />} title="Stocks & current assets" detail="Liquid and market-linked holdings" />
        <Table size="small"><TableHead><TableRow><TableCell>Asset</TableCell><TableCell align="right">Principal</TableCell><TableCell align="right">Market</TableCell><TableCell align="right">Gain</TableCell></TableRow></TableHead><TableBody>
          {currentAssets.map((asset) => <TableRow key={asset.name}><TableCell><Stack direction="row" gap={1.25} alignItems="center">{assetIconFor(asset.name)}<Box><Typography variant="body2" fontWeight={700}>{asset.name}</Typography><Typography variant="caption" color="text.secondary">{asset.detail}</Typography></Box></Stack></TableCell><TableCell align="right">{asset.principal}</TableCell><TableCell align="right">{asset.market}</TableCell><TableCell align="right" sx={{ color: asset.gain.startsWith('+') ? 'success.main' : 'text.secondary', fontWeight: 700 }}>{asset.gain}</TableCell></TableRow>)}
        </TableBody></Table>
      </Paper>
      <Paper variant="outlined" sx={{ p: 2, overflowX: 'auto' }}>
        <PortfolioSectionHeader icon={assetIconFor('Property')} title="Fixed assets" detail="46% of workbook net worth" />
        <Table size="small"><TableHead><TableRow><TableCell>Asset</TableCell><TableCell align="right">Principal</TableCell><TableCell align="right">Market</TableCell></TableRow></TableHead><TableBody>
          {fixedAssets.map((asset) => <TableRow key={asset.name}><TableCell><Stack direction="row" gap={1.25} alignItems="center">{assetIconFor(asset.type === 'Office' ? 'Office' : 'Property')}<Box><Typography variant="body2" fontWeight={700}>{asset.name}</Typography><Typography variant="caption" color="text.secondary">{asset.type}</Typography></Box></Stack></TableCell><TableCell align="right">{asset.principal}</TableCell><TableCell align="right">{asset.market}</TableCell></TableRow>)}
        </TableBody></Table>
      </Paper>
    </Box>
);

export const PortfolioBalanceSheet: React.FC = () => (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <PortfolioSectionHeader icon={<BalanceRoundedIcon fontSize="small" />} title="Balance sheet — year wise" detail="All values ₹ Cr" />
      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: '1.35fr 1fr' }, gap: 3, alignItems: 'center' }}>
        <Box sx={{ overflowX: 'auto' }}><Table size="small"><TableHead><TableRow><TableCell>Measure</TableCell>{history.map((item) => <TableCell key={item.year} align="right">{item.year}</TableCell>)}</TableRow></TableHead><TableBody>
          <TableRow><TableCell>Total principal</TableCell>{history.map((item) => <TableCell key={item.year} align="right">{item.principal.toFixed(2)}</TableCell>)}</TableRow>
          <TableRow><TableCell>Total market value</TableCell>{history.map((item) => <TableCell key={item.year} align="right" sx={{ fontWeight: 700 }}>{item.market.toFixed(2)}</TableCell>)}</TableRow>
          <TableRow><TableCell>Savings added</TableCell>{history.map((item) => <TableCell key={item.year} align="right">{item.savings.toFixed(2)}</TableCell>)}</TableRow>
          <TableRow><TableCell>Profit % (current assets)</TableCell>{history.map((item) => <TableCell key={item.year} align="right" sx={{ color: 'success.main' }}>{item.profit.toFixed(1)}%</TableCell>)}</TableRow>
        </TableBody></Table></Box>
        <Box sx={{ height: 210 }}><ResponsiveContainer width="100%" height="100%"><BarChart data={history} margin={{ top: 22 }}><CartesianGrid stroke="#E9EEF5" vertical={false} strokeDasharray="3 4" /><XAxis dataKey="year" tick={{ fontSize: 11 }} /><YAxis tick={{ fontSize: 10 }} tickFormatter={(value) => `${value} Cr`} /><Tooltip formatter={(value: number) => croreLabel(value)} /><Legend /><Bar dataKey="principal" name="Principal" fill="#C8CDD6" radius={[4, 4, 0, 0]} isAnimationActive={false} /><Bar dataKey="market" name="Market value" fill="#2E7CF6" radius={[4, 4, 0, 0]} isAnimationActive={false}><LabelList dataKey="market" position="top" formatter={(value: number) => `₹${value.toFixed(1)} Cr`} style={{ fill: '#175CD3', fontSize: 10, fontWeight: 700 }} /></Bar></BarChart></ResponsiveContainer></Box>
      </Box>
    </Paper>
);

const PortfolioWorkbookSnapshot: React.FC = () => (
  <Stack spacing={2}>
    <PortfolioWealthGrowth />
    <PortfolioAssetPanels />
    <PortfolioBalanceSheet />
  </Stack>
);

export default PortfolioWorkbookSnapshot;
