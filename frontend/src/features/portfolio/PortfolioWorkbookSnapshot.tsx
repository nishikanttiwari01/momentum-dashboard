import React from 'react';
import { Box, Paper, Stack, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material';
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

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

const heading = (color: string, title: string, detail?: string) => (
  <Stack direction="row" alignItems="center" gap={1} sx={{ mb: 1.25 }}>
    <Box sx={{ width: 8, height: 8, borderRadius: 0.5, bgcolor: color }} />
    <Typography variant="overline" fontWeight={700} letterSpacing="0.12em">{title}</Typography>
    {detail ? <Typography variant="caption" color="text.secondary">{detail}</Typography> : null}
  </Stack>
);

export const PortfolioWealthGrowth: React.FC = () => (
    <Paper data-testid="portfolio-wealth-growth" variant="outlined" sx={{ p: 2, height: '100%', boxSizing: 'border-box' }}>
      {heading('#06aed4', 'Wealth growth over years', '₹ Cr · workbook snapshots')}
      <Box sx={{ height: 210 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={history} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="#eef1f5" vertical={false} />
            <XAxis dataKey="year" tick={{ fontSize: 11 }} />
            <YAxis domain={[4, 9]} tick={{ fontSize: 11 }} tickFormatter={(value) => `₹${value} Cr`} width={58} />
            <Tooltip formatter={(value: number) => [`₹${value.toFixed(2)} Cr`]} />
            <Legend />
            <Line type="monotone" dataKey="principal" name="Principal" stroke="#98a2b3" strokeWidth={2} />
            <Line type="monotone" dataKey="market" name="Market value" stroke="#2e90fa" strokeWidth={2.5} />
          </LineChart>
        </ResponsiveContainer>
      </Box>
      <Stack direction="row" justifyContent="flex-end"><Typography variant="caption" color="text.secondary">Latest market value <b>₹8.31 Cr</b></Typography></Stack>
    </Paper>
);

export const PortfolioAssetPanels: React.FC = () => (
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: '1.2fr 1fr' }, gap: 2 }}>
      <Paper variant="outlined" sx={{ p: 2, overflowX: 'auto' }}>
        {heading('#00b386', 'Stocks & current assets')}
        <Table size="small"><TableHead><TableRow><TableCell>Asset</TableCell><TableCell align="right">Principal</TableCell><TableCell align="right">Market</TableCell><TableCell align="right">Gain</TableCell></TableRow></TableHead><TableBody>
          {currentAssets.map((asset) => <TableRow key={asset.name}><TableCell><Typography variant="body2" fontWeight={700}>{asset.name}</Typography><Typography variant="caption" color="text.secondary">{asset.detail}</Typography></TableCell><TableCell align="right">{asset.principal}</TableCell><TableCell align="right">{asset.market}</TableCell><TableCell align="right" sx={{ color: asset.gain.startsWith('+') ? 'success.main' : 'text.secondary' }}>{asset.gain}</TableCell></TableRow>)}
        </TableBody></Table>
      </Paper>
      <Paper variant="outlined" sx={{ p: 2, overflowX: 'auto' }}>
        {heading('#f79009', 'Fixed assets', '46% of workbook net worth')}
        <Table size="small"><TableHead><TableRow><TableCell>Asset</TableCell><TableCell align="right">Principal</TableCell><TableCell align="right">Market</TableCell></TableRow></TableHead><TableBody>
          {fixedAssets.map((asset) => <TableRow key={asset.name}><TableCell><Typography variant="body2" fontWeight={700}>{asset.name}</Typography><Typography variant="caption" color="text.secondary">{asset.type}</Typography></TableCell><TableCell align="right">{asset.principal}</TableCell><TableCell align="right">{asset.market}</TableCell></TableRow>)}
        </TableBody></Table>
      </Paper>
    </Box>
);

export const PortfolioBalanceSheet: React.FC = () => (
    <Paper variant="outlined" sx={{ p: 2 }}>
      {heading('#06aed4', 'Balance sheet — year wise', 'all values ₹ Cr')}
      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: '1.35fr 1fr' }, gap: 3, alignItems: 'center' }}>
        <Box sx={{ overflowX: 'auto' }}><Table size="small"><TableHead><TableRow><TableCell>Measure</TableCell>{history.map((item) => <TableCell key={item.year} align="right">{item.year}</TableCell>)}</TableRow></TableHead><TableBody>
          <TableRow><TableCell>Total principal</TableCell>{history.map((item) => <TableCell key={item.year} align="right">{item.principal.toFixed(2)}</TableCell>)}</TableRow>
          <TableRow><TableCell>Total market value</TableCell>{history.map((item) => <TableCell key={item.year} align="right" sx={{ fontWeight: 700 }}>{item.market.toFixed(2)}</TableCell>)}</TableRow>
          <TableRow><TableCell>Savings added</TableCell>{history.map((item) => <TableCell key={item.year} align="right">{item.savings.toFixed(2)}</TableCell>)}</TableRow>
          <TableRow><TableCell>Profit % (current assets)</TableCell>{history.map((item) => <TableCell key={item.year} align="right" sx={{ color: 'success.main' }}>{item.profit.toFixed(1)}%</TableCell>)}</TableRow>
        </TableBody></Table></Box>
        <Box sx={{ height: 210 }}><ResponsiveContainer width="100%" height="100%"><BarChart data={history}><CartesianGrid stroke="#eef1f5" vertical={false} /><XAxis dataKey="year" tick={{ fontSize: 11 }} /><YAxis tick={{ fontSize: 10 }} tickFormatter={(value) => `${value} Cr`} /><Tooltip /><Legend /><Bar dataKey="principal" name="Principal" fill="#c8cdd6" radius={[3, 3, 0, 0]} /><Bar dataKey="market" name="Market value" fill="#2e90fa" radius={[3, 3, 0, 0]} /></BarChart></ResponsiveContainer></Box>
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
