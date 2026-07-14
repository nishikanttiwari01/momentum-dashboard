import React from 'react';
import { Box, Stack, Typography } from '@mui/material';
import AccountBalanceWalletRoundedIcon from '@mui/icons-material/AccountBalanceWalletRounded';
import BusinessRoundedIcon from '@mui/icons-material/BusinessRounded';
import HomeWorkRoundedIcon from '@mui/icons-material/HomeWorkRounded';
import SavingsRoundedIcon from '@mui/icons-material/SavingsRounded';
import ShowChartRoundedIcon from '@mui/icons-material/ShowChartRounded';

const iconMeta = (name: string) => {
  const value = name.toLowerCase();
  if (value.includes('mutual') || value.includes('fund')) return { key: 'mutual-funds', color: '#2E7CF6', bg: '#EAF2FF', icon: <AccountBalanceWalletRoundedIcon fontSize="small" /> };
  if (value.includes('stock')) return { key: 'stocks', color: '#06AED4', bg: '#E8F9FC', icon: <ShowChartRoundedIcon fontSize="small" /> };
  if (value.includes('debt') || value.includes('saving')) return { key: 'savings', color: '#12B76A', bg: '#ECFDF3', icon: <SavingsRoundedIcon fontSize="small" /> };
  if (value.includes('office')) return { key: 'office', color: '#7A5AF8', bg: '#F1EEFF', icon: <BusinessRoundedIcon fontSize="small" /> };
  return { key: 'property', color: '#F79009', bg: '#FFF4E5', icon: <HomeWorkRoundedIcon fontSize="small" /> };
};

export const assetIconFor = (name: string) => {
  const meta = iconMeta(name);
  return <Box data-portfolio-icon={meta.key} aria-hidden="true" sx={{ display: 'flex', color: meta.color }}>{meta.icon}</Box>;
};

export const PortfolioIconTile: React.FC<{ children: React.ReactNode; color?: string; background?: string }> = ({ children, color = '#2E7CF6', background = '#EAF2FF' }) => (
  <Box sx={{ width: 34, height: 34, flex: '0 0 auto', borderRadius: 2, display: 'grid', placeItems: 'center', color, bgcolor: background }}>{children}</Box>
);

export const PortfolioSectionHeader: React.FC<{ icon: React.ReactNode; title: string; detail?: string }> = ({ icon, title, detail }) => (
  <Stack direction="row" alignItems="center" gap={1.1} sx={{ mb: 1.5 }}>
    <PortfolioIconTile>{icon}</PortfolioIconTile>
    <Box>
      <Typography variant="subtitle2" sx={{ fontWeight: 800, color: '#14213D', letterSpacing: '0.025em' }}>{title}</Typography>
      {detail ? <Typography variant="caption" color="text.secondary">{detail}</Typography> : null}
    </Box>
  </Stack>
);

export const PortfolioMetricTile: React.FC<{ icon: React.ReactNode; label: string; value: string; tone?: 'positive' | 'neutral' }> = ({ icon, label, value, tone = 'neutral' }) => (
  <Stack data-tone={tone} direction="row" alignItems="center" gap={1.25} sx={{ minWidth: 155, px: 1.5, py: 1, borderRadius: 2.5, bgcolor: tone === 'positive' ? '#F0FDF6' : '#F7F9FC', border: '1px solid', borderColor: tone === 'positive' ? '#C6F0D8' : '#E7EBF2' }}>
    <PortfolioIconTile color={tone === 'positive' ? '#12B76A' : '#2E7CF6'} background={tone === 'positive' ? '#DCFCE8' : '#EAF2FF'}>{icon}</PortfolioIconTile>
    <Box>
      <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase', letterSpacing: '0.06em' }}>{label}</Typography>
      <Typography variant="subtitle1" sx={{ fontWeight: 800, color: tone === 'positive' ? '#079455' : '#14213D', fontVariantNumeric: 'tabular-nums', lineHeight: 1.25 }}>{value}</Typography>
    </Box>
  </Stack>
);
