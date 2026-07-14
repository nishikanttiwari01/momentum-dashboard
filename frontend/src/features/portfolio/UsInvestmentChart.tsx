import * as React from 'react';
import { Alert, Box, CircularProgress, Stack, Table, TableBody, TableCell, TableHead, TableRow, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import axios from 'axios';
import dayjs from 'dayjs';
import { CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from 'recharts';
import { UsHistory, UsTransaction, usd } from './usPortfolioTypes';

const ranges = ['1m', '6m', '1y', '5y', 'max'] as const;

export default function UsInvestmentChart({ transactions }: { transactions: UsTransaction[] }) {
  const [range, setRange] = React.useState<(typeof ranges)[number]>('1y');
  const query = useQuery({
    queryKey: ['us-portfolio-history', 'qqq', range],
    queryFn: async () => (await axios.get<UsHistory>('/api/v1/portfolio/us/qqq/history', { params: { range } })).data,
    staleTime: 30 * 60 * 1000,
  });
  const data = query.data;
  const prices = (data?.points || []).map(p => ({ x: new Date(`${p.date}T12:00:00Z`).getTime(), price: p.price }));
  const purchases = (data?.purchases || []).map(p => ({ x: new Date(p.purchased_at).getTime(), purchasePrice: p.price_usd, transaction: p }));
  return <Box sx={{ p: 2 }}>
    <Stack direction="row" alignItems="center" spacing={2} flexWrap="wrap" useFlexGap>
      <Typography fontWeight={700}>QQQ price and purchases</Typography>
      {data?.latest_vs_average_pct != null && <Typography color={data.latest_vs_average_pct <= 0 ? 'success.main' : 'warning.main'}>
        Latest is {Math.abs(data.latest_vs_average_pct).toFixed(2)}% {data.latest_vs_average_pct < 0 ? 'below' : 'above'} average cost
      </Typography>}
      <Box sx={{ flexGrow: 1 }} />
      <ToggleButtonGroup size="small" exclusive value={range} onChange={(_, v) => v && setRange(v)}>
        {ranges.map(r => <ToggleButton key={r} value={r}>{r === 'max' ? 'Max' : r.toUpperCase()}</ToggleButton>)}
      </ToggleButtonGroup>
    </Stack>
    {query.isLoading ? <Stack alignItems="center" sx={{ py: 6 }}><CircularProgress /></Stack> : data?.error ? <Alert severity="warning" sx={{ mt: 2 }}>{data.error}</Alert> :
      <Box sx={{ height: 300, mt: 1 }}><ResponsiveContainer width="100%" height="100%"><ComposedChart margin={{ top: 10, right: 20, bottom: 0, left: 5 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="x" type="number" scale="time" domain={['dataMin', 'dataMax']} tickFormatter={v => dayjs(v).format('MMM YY')} />
        <YAxis domain={['auto', 'auto']} tickFormatter={v => `$${Number(v).toFixed(0)}`} />
        <Tooltip labelFormatter={v => dayjs(Number(v)).format('DD MMM YYYY, HH:mm')} formatter={(v: any, name: string, item: any) => {
          if (name === 'purchasePrice') { const t = item.payload.transaction; return [`${usd(v)} · ${t.quantity} units · fees ${usd(t.fees_usd)}`, 'Purchase']; }
          return [usd(Number(v)), 'QQQ price'];
        }} />
        <Line data={prices} dataKey="price" stroke="#2f80ed" strokeWidth={1.8} dot={false} isAnimationActive={false} />
        <Scatter data={purchases} dataKey="purchasePrice" fill="#f59e0b" shape="circle" />
        {data?.average_buy_price_usd != null && <ReferenceLine y={data.average_buy_price_usd} stroke="#8b5cf6" strokeDasharray="6 4" label={{ value: `Avg ${usd(data.average_buy_price_usd)}`, position: 'insideTopRight' }} />}
      </ComposedChart></ResponsiveContainer></Box>}
    <Typography variant="subtitle2" sx={{ mt: 2 }}>Purchase history</Typography>
    <Table size="small"><TableHead><TableRow><TableCell>Date</TableCell><TableCell align="right">Units</TableCell><TableCell align="right">Price</TableCell><TableCell align="right">Fees</TableCell><TableCell align="right">Invested</TableCell></TableRow></TableHead>
      <TableBody>{transactions.map(t => <TableRow key={t.id}><TableCell>{dayjs(t.purchased_at).format('DD MMM YYYY, HH:mm')}</TableCell><TableCell align="right">{t.quantity}</TableCell><TableCell align="right">{usd(t.price_usd)}</TableCell><TableCell align="right">{usd(t.fees_usd)}</TableCell><TableCell align="right">{usd(t.invested_usd)}</TableCell></TableRow>)}</TableBody></Table>
  </Box>;
}
