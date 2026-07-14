import * as React from 'react';
import { Alert, Button, CircularProgress, Paper, Stack, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import AddUsTransactionDialog from './AddUsTransactionDialog';
import UsInvestmentChart from './UsInvestmentChart';
import { UsOverview, usd } from './usPortfolioTypes';

export default function UsInvestmentsSection() {
  const [expanded, setExpanded] = React.useState(false), [dialog, setDialog] = React.useState(false);
  const client = useQueryClient();
  const query = useQuery({ queryKey: ['us-portfolio-overview'], queryFn: async () => (await axios.get<UsOverview>('/api/v1/portfolio/us/overview')).data, retry: 1 });
  const row = query.data?.instruments[0];
  const saved = async () => { await client.invalidateQueries({ queryKey: ['us-portfolio-overview'] }); await client.invalidateQueries({ queryKey: ['us-portfolio-history', 'qqq'] }); };
  return <Paper sx={{ p: 2, overflowX: 'auto' }}>
    <Stack direction="row" alignItems="center" sx={{ mb: 1 }}><Typography variant="subtitle1" fontWeight={700}>US Investments</Typography><Typography variant="caption" color="text.secondary" sx={{ ml: 1 }}>USD · separate from INR totals</Typography></Stack>
    {query.isLoading ? <CircularProgress size={24} /> : query.isError || !row ? <Alert severity="error">Could not load US investments.</Alert> : <>
      {row.market_data_error && <Alert severity="warning" sx={{ mb: 1 }}>{row.market_data_error}. Your purchases remain available.</Alert>}
      <Table size="small"><TableHead><TableRow><TableCell>Fund</TableCell><TableCell align="right">Latest price</TableCell><TableCell align="right">Units</TableCell><TableCell align="right">Invested</TableCell><TableCell align="right">Average price</TableCell><TableCell align="right">Current value</TableCell><TableCell align="right">Gain / loss</TableCell><TableCell align="right">Action</TableCell></TableRow></TableHead>
        <TableBody><TableRow hover selected={expanded} onClick={() => setExpanded(!expanded)} sx={{ cursor: 'pointer' }}><TableCell><Typography fontWeight={700}>QQQ</Typography><Typography variant="caption">{row.name}</Typography></TableCell><TableCell align="right">{usd(row.latest_price_usd)}</TableCell><TableCell align="right">{row.holding.total_units}</TableCell><TableCell align="right">{usd(row.holding.total_invested_usd)}</TableCell><TableCell align="right">{usd(row.holding.average_buy_price_usd)}</TableCell><TableCell align="right">{usd(row.holding.current_value_usd)}</TableCell><TableCell align="right" sx={{ color: (row.holding.unrealized_gain_usd || 0) >= 0 ? 'success.main' : 'error.main' }}>{usd(row.holding.unrealized_gain_usd)} {row.holding.unrealized_gain_pct != null ? `(${row.holding.unrealized_gain_pct.toFixed(2)}%)` : ''}</TableCell><TableCell align="right"><Button size="small" startIcon={<AddIcon />} onClick={e => { e.stopPropagation(); setDialog(true); }}>Add transaction</Button></TableCell></TableRow>
          {expanded && <TableRow><TableCell colSpan={8} sx={{ p: 0, bgcolor: 'action.hover' }}><UsInvestmentChart transactions={row.transactions} /></TableCell></TableRow>}</TableBody></Table>
      {!row.transactions.length && <Typography variant="caption" color="text.secondary">Add your first QQQ purchase to calculate average cost.</Typography>}
      <AddUsTransactionDialog open={dialog} onClose={() => setDialog(false)} onSaved={saved} />
    </>}
  </Paper>;
}
