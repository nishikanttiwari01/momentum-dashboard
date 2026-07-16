import React from 'react';
import { Alert, Box, Chip, Paper, Skeleton, Stack, Typography } from '@mui/material';
import AccountBalanceWalletRoundedIcon from '@mui/icons-material/AccountBalanceWalletRounded';
import CurrencyExchangeRoundedIcon from '@mui/icons-material/CurrencyExchangeRounded';
import { useQuery } from '@tanstack/react-query';
import { fetchWealthSummary } from './wealthApi';
import type { WealthSummary } from './wealthTypes';

const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 });

function wealthMoney(value: number | null): string {
  if (value == null) return '—';
  if (Math.abs(value) >= 10_000_000) return `₹${(value / 10_000_000).toFixed(2)} Cr`;
  return inr.format(value);
}

export const PortfolioSummaryHeaderView: React.FC<{ summary: WealthSummary }> = ({ summary }) => {
  if (summary.data_health === 'empty') {
    return <Alert severity="info">Import investment.xlsx to build consolidated wealth. Existing investment tracking remains available below.</Alert>;
  }
  return <Paper variant="outlined" sx={{ p: 2, borderRadius: 3, borderColor: '#DCE5F0', boxShadow: '0 12px 32px rgba(22,34,58,0.06)' }}>
    <Stack direction={{ xs: 'column', md: 'row' }} spacing={2.5} alignItems={{ md: 'center' }}>
      <Box sx={{ minWidth: 260 }}><Typography variant="overline" color="text.secondary" fontWeight={800}>Net worth market value</Typography><Typography variant="h4" fontWeight={900}>{wealthMoney(summary.net_worth_market_value_inr)}</Typography><Typography variant="caption" color="text.secondary">Combined household value · property included</Typography></Box>
      <Box><Typography variant="caption" color="text.secondary">Invested capital</Typography><Typography variant="h6" fontWeight={800}>{wealthMoney(summary.invested_capital_inr)}</Typography></Box>
      <Box><Typography variant="caption" color="text.secondary">Investment XIRR</Typography><Typography variant="h6" fontWeight={800}>{summary.investment_xirr_pct == null ? 'Pending complete history' : `${summary.investment_xirr_pct.toFixed(2)}%`}</Typography></Box>
      <Box sx={{ flexGrow: 1 }} />
      {summary.fx ? <Chip icon={<CurrencyExchangeRoundedIcon />} variant="outlined" color={summary.fx.is_fallback ? 'warning' : 'success'} label={`USD/INR ${summary.fx.rate.toFixed(2)} · ${summary.fx.effective_on}${summary.fx.is_fallback ? ' cached' : ''}`} /> : null}
      <Chip icon={<AccountBalanceWalletRoundedIcon />} label={`As of ${summary.as_of ?? '—'}`} />
    </Stack>
  </Paper>;
};

const PortfolioSummaryHeader: React.FC = () => {
  const query = useQuery({ queryKey: ['wealth-summary'], queryFn: fetchWealthSummary, staleTime: 5 * 60 * 1000, retry: 1 });
  if (query.isLoading) return <Paper variant="outlined" sx={{ p: 2 }}><Skeleton width="35%" height={32} /><Skeleton width="65%" /></Paper>;
  if (!query.data || query.isError) return <Alert severity="warning">Consolidated wealth is temporarily unavailable. Existing investment tracking remains available.</Alert>;
  return <PortfolioSummaryHeaderView summary={query.data} />;
};

export default PortfolioSummaryHeader;
