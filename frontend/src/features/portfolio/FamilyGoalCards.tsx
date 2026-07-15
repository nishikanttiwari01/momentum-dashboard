import React from 'react';
import { Box, Chip, Typography } from '@mui/material';
import FavoriteBorderRounded from '@mui/icons-material/FavoriteBorderRounded';
import HomeWorkOutlined from '@mui/icons-material/HomeWorkOutlined';
import PaymentsOutlined from '@mui/icons-material/PaymentsOutlined';
import SchoolOutlined from '@mui/icons-material/SchoolOutlined';
import { formatCrore, goalStatusColor } from './familyWealthMath';
import type { FamilyGoalType, GoalHealth } from './wealthTypes';

const ICONS: Record<FamilyGoalType, { label: string; icon: React.ElementType }> = {
  education: { label: 'Education goal', icon: SchoolOutlined }, house: { label: 'House goal', icon: HomeWorkOutlined }, marriage: { label: 'Marriage goal', icon: FavoriteBorderRounded }, passive_income: { label: 'Passive income goal', icon: PaymentsOutlined },
};
const formatDate = (date: string | null | undefined) => date ? new Intl.DateTimeFormat('en-IN', { month: 'short', year: 'numeric', timeZone: 'UTC' }).format(new Date(date)) : '—';

export const FamilyGoalCards: React.FC<{ goals: readonly GoalHealth[] }> = ({ goals }) => <Box component="section" aria-label="Family goal health" sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 250px), 1fr))', gap: 1.5 }}>
  {goals.map((health) => {
    const icon = ICONS[health.goal.goal_type]; const Icon = icon.icon; const status = health.status[0].toUpperCase() + health.status.slice(1);
    return <Box component="article" key={health.goal.goal_key} sx={{ bgcolor: '#fff', border: '1px solid #DCE7F2', borderTop: `3px solid ${goalStatusColor(health.status)}`, borderRadius: 2.5, p: 2 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1, alignItems: 'flex-start' }}><Box sx={{ display: 'flex', gap: 1 }}><Icon aria-label={icon.label} sx={{ color: '#2563EB' }} /><Box><Typography fontWeight={800} color="#102A43">{health.goal.name || '—'}</Typography><Typography variant="caption" color="text.secondary">Due {formatDate(health.goal.target_date)}</Typography></Box></Box><Chip size="small" label={status} sx={{ color: goalStatusColor(health.status), fontWeight: 800 }} /></Box>
      <Typography variant="h6" sx={{ mt: 1.5, color: '#102A43', fontWeight: 800 }}>{Number.isFinite(health.funded_pct) ? `${health.funded_pct}% funded` : '—'}</Typography>
      <Typography variant="body2">Inflated cost {formatCrore(health.inflated_cost_inr)}</Typography>
      <Typography variant="body2">Available {formatCrore(health.available_before_inr)}</Typography>
      <Typography variant="body2" sx={{ color: health.shortfall_inr > 0 ? '#B3261E' : '#137333', fontWeight: 700 }}>{health.shortfall_inr > 0 ? `Gap ${formatCrore(health.shortfall_inr)}` : `Funded ${formatCrore(health.funded_amount_inr)}`}</Typography>
      <Typography variant="caption" display="block" sx={{ mt: 1, color: '#52677C' }}>{health.reason || '—'}</Typography>
    </Box>;
  })}
</Box>;

export default FamilyGoalCards;
