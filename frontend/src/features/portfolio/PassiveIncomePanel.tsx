import React from 'react';
import { Box, Chip, Typography } from '@mui/material';
import { formatCrore, formatMonthlyIncome } from './familyWealthMath';
import type { PassiveIncomeAnalysis } from './wealthTypes';

type NullableIncomeFact = 'target_monthly_income_inr' | 'projected_monthly_rent_inr' | 'portfolio_monthly_gap_inr' | 'required_corpus_inr' | 'supported_portfolio_monthly_income_inr' | 'total_monthly_income_inr' | 'surplus_or_shortfall_inr';
export type PassiveIncomePanelData = Omit<PassiveIncomeAnalysis, NullableIncomeFact> & { [Key in NullableIncomeFact]: number | null };

const dateLabel = (date: string | null) => date ? new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(new Date(date)) : '—';
const signedMonthly = (value: number | null | undefined) => value == null ? '—' : `${value > 0 ? '+' : ''}${formatMonthlyIncome(value)}`;

export const PassiveIncomePanel: React.FC<{ analysis: PassiveIncomePanelData }> = ({ analysis }) => <Box component="section" aria-labelledby="passive-income-title" sx={{ bgcolor: '#F5F9FE', border: '1px solid #CFE0F2', borderLeft: `5px solid ${analysis.on_track ? '#0F9D8A' : '#DC4C4C'}`, borderRadius: 3, p: { xs: 2, md: 3 } }}>
  <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 2, flexWrap: 'wrap' }}><Box><Typography id="passive-income-title" variant="h6" fontWeight={800} color="#102A43">{analysis.target_date?.slice(0, 4) || '—'} income runway</Typography><Typography variant="body2">Rent counts toward the {formatMonthlyIncome(analysis.target_monthly_income_inr)} target</Typography></Box><Chip label={analysis.on_track ? 'On track' : 'Shortfall'} color={analysis.on_track ? 'success' : 'error'} /></Box>
  <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'repeat(3, 1fr)' }, gap: 2, my: 2 }}>
    <Box><Typography variant="caption">Monthly target</Typography><Typography fontWeight={800}>{formatMonthlyIncome(analysis.target_monthly_income_inr)}</Typography><Typography variant="body2">Rent {formatMonthlyIncome(analysis.projected_monthly_rent_inr)}</Typography></Box>
    <Box><Typography variant="caption">Portfolio requirement</Typography><Typography fontWeight={800}>{formatMonthlyIncome(analysis.portfolio_monthly_gap_inr)}</Typography><Typography variant="body2">Corpus at withdrawal {formatCrore(analysis.required_corpus_inr)}</Typography></Box>
    <Box><Typography variant="caption">Projected support</Typography><Typography fontWeight={800}>{formatMonthlyIncome(analysis.total_monthly_income_inr)}</Typography><Typography variant="body2">Portfolio {formatMonthlyIncome(analysis.supported_portfolio_monthly_income_inr)}</Typography></Box>
  </Box>
  <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 2, borderTop: '1px solid #CFE0F2', pt: 1.5, flexWrap: 'wrap' }}><Box><Typography variant="caption">Surplus / shortfall</Typography><Typography fontWeight={800} color={(analysis.surplus_or_shortfall_inr ?? 0) >= 0 ? '#137333' : '#B3261E'}>{signedMonthly(analysis.surplus_or_shortfall_inr)}</Typography></Box><Box><Typography component="span" variant="caption">Earliest sustainable date</Typography><strong style={{ display: 'block' }}>{dateLabel(analysis.earliest_sustainable_date)}</strong></Box></Box>
  <Typography variant="body2" sx={{ mt: 1.5, fontWeight: 700, color: analysis.later_goals_protected ? '#0F766E' : '#B3261E' }}>{analysis.later_goals_protected ? 'Later goals remain protected after income withdrawals.' : 'Later goals would be exposed by this income plan; increase the corpus or move the start date.'}</Typography>
</Box>;

export default PassiveIncomePanel;
