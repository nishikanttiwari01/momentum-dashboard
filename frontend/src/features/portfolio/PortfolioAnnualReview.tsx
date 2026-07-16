import React from 'react';
import { Alert, Box, Button, Chip, MenuItem, Paper, Select, Skeleton, Stack, Table, TableBody, TableCell, TableHead, TableRow, Tooltip, Typography } from '@mui/material';
import EditRoundedIcon from '@mui/icons-material/EditRounded';
import AddRoundedIcon from '@mui/icons-material/AddRounded';
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, XAxis, YAxis } from 'recharts';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import AnnualReviewEditor from './AnnualReviewEditor';
import { deleteAnnualReviewOverrides, fetchAnnualReviews, saveAnnualReviewOverrides } from './wealthApi';
import type { AnnualReviewField, AnnualReviewOverrideUpdate, AnnualReviewResponse } from './wealthTypes';

const money = (value: number | null) => value == null ? 'Missing' : `${value < 0 ? '−' : ''}₹${(Math.abs(value) / 10_000_000).toFixed(2)} Cr`;
const sourceLabel = (source: AnnualReviewField['source']) => source === 'manual' ? 'Manual override' : source[0].toUpperCase() + source.slice(1);
const sourceColor = (source: AnnualReviewField['source']) => source === 'manual' ? 'warning' : source === 'missing' ? 'default' : 'info';
const keyFields: { key: keyof AnnualReviewResponse; label: string; color: string; percent?: boolean }[] = [
  { key: 'opening_net_worth_inr', label: 'Opening value', color: '#475569' },
  { key: 'contributions_inr', label: 'Cash deployed', color: '#2563EB' },
  { key: 'investment_gain_inr', label: 'Investment gain', color: '#0891B2' },
  { key: 'property_gain_inr', label: 'Property gain', color: '#7C3AED' },
  { key: 'rent_received_inr', label: 'Rent received', color: '#D97706' },
  { key: 'withdrawals_inr', label: 'Withdrawals', color: '#EA580C' },
  { key: 'closing_net_worth_inr', label: 'Closing value', color: '#059669' },
  { key: 'investment_xirr_pct', label: 'Investment XIRR', color: '#059669', percent: true },
];

const reconciliationMeta = {
  reconciled: { label: 'Reconciled', color: 'success' as const, message: 'Opening wealth and annual movements reconcile to closing wealth.' },
  needs_review: { label: 'Needs review', color: 'warning' as const, message: 'The entered movements do not reconcile to closing wealth.' },
  incomplete: { label: 'Incomplete', color: 'default' as const, message: 'Enter the missing values to complete this year.' },
};

type ViewProps = { reviews: AnnualReviewResponse[]; selectedYear: number; onSelectYear: (year: number) => void; onEdit: () => void; onAddYear?: () => void };
export const PortfolioAnnualReviewView: React.FC<ViewProps> = ({ reviews, selectedYear, onSelectYear, onEdit, onAddYear }) => {
  const row = reviews.find(item => item.year === selectedYear) ?? reviews[0];
  if (!row) return null;
  const bridge = keyFields.slice(0, 7).map(item => ({ name: item.label.replace(' value', ''), value: (row[item.key] as AnnualReviewField).value == null ? 0 : (row[item.key] as AnnualReviewField).value! / 10_000_000, color: item.color }));
  const reconciliation = reconciliationMeta[row.reconciliation.status];
  return <Stack spacing={1.5}>
    <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ sm: 'center' }} gap={1}>
      <Box><Typography variant="h6" fontWeight={800}>Annual wealth review</Typography><Typography variant="body2" color="text.secondary">January–December · calculated from portfolio data with manual overrides only where needed</Typography></Box>
      <Stack direction="row" gap={1}><Select size="small" value={row.year} onChange={event => onSelectYear(Number(event.target.value))} aria-label="Review year">{reviews.map(item => <MenuItem key={item.year} value={item.year}>{item.year}</MenuItem>)}</Select>{onAddYear ? <Button startIcon={<AddRoundedIcon/>} onClick={onAddYear}>Add year</Button> : null}<Button variant="outlined" startIcon={<EditRoundedIcon/>} onClick={onEdit}>Edit year</Button></Stack>
    </Stack>

    <Alert severity={reconciliation.color === 'default' ? 'info' : reconciliation.color} action={<Chip size="small" label={reconciliation.label} color={reconciliation.color} variant="outlined"/>}>{reconciliation.message}{row.reconciliation.difference_inr != null && row.reconciliation.status === 'needs_review' ? ` Difference ${money(row.reconciliation.difference_inr)}.` : ''}</Alert>

    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: 'repeat(2, 1fr)', md: 'repeat(4, 1fr)' }, gap: 1 }}>
      {keyFields.map(({ key, label, color, percent }) => { const field = row[key] as AnnualReviewField; return <Tooltip key={key} title={field.explanation}><Paper variant="outlined" sx={{ p: 1.35, borderRadius: 2.25, borderColor: '#E5EAF1' }}><Stack direction="row" justifyContent="space-between" alignItems="start"><Typography variant="caption" color="text.secondary">{label}</Typography><Chip size="small" label={sourceLabel(field.source)} color={sourceColor(field.source)} variant="outlined" sx={{ height: 19, fontSize: 9 }}/></Stack><Typography sx={{ color: field.value == null ? 'text.disabled' : color, fontWeight: 800, fontSize: 18 }}>{percent ? field.value == null ? 'Missing' : `${field.value}%` : money(field.value)}</Typography></Paper></Tooltip>; })}
    </Box>

    <Paper variant="outlined" sx={{ p: 2, borderRadius: 2.5, borderColor: '#E5EAF1' }}><Typography fontWeight={800}>{row.year} wealth bridge</Typography><Typography variant="caption" color="text.secondary">Effective values after applying manual overrides · ₹ Cr</Typography><Box sx={{ height: 265, mt: 1 }}><ResponsiveContainer width="100%" height="100%"><BarChart data={bridge} margin={{ top: 18, right: 10, left: -10 }}><CartesianGrid stroke="#E9EEF5" vertical={false} strokeDasharray="3 4"/><XAxis dataKey="name" tick={{ fontSize: 10 }}/><YAxis tick={{ fontSize: 10 }} tickFormatter={value => `₹${value}`}/><Bar dataKey="value" radius={[7, 7, 0, 0]} isAnimationActive={false}>{bridge.map(item => <Cell key={item.name} fill={item.color}/>)}</Bar></BarChart></ResponsiveContainer></Box></Paper>

    <Paper variant="outlined" sx={{ borderRadius: 2.5, borderColor: '#E5EAF1', overflow: 'hidden' }}><Box sx={{ p: 1.5 }}><Typography fontWeight={800}>Year-by-year scorecard</Typography><Typography variant="caption" color="text.secondary">Select a row to review or edit that year</Typography></Box><Box sx={{ overflowX: 'auto' }}><Table size="small"><TableHead><TableRow sx={{ bgcolor: '#F8FAFC' }}>{['Year', 'Opening', 'Contributions', 'Investment gain', 'Property gain', 'Rent', 'Withdrawals', 'Closing', 'XIRR', 'Status'].map(label => <TableCell key={label} align={label === 'Year' || label === 'Status' ? 'left' : 'right'} sx={{ fontWeight: 700 }}>{label}</TableCell>)}</TableRow></TableHead><TableBody>{reviews.map(item => <TableRow key={item.year} selected={item.year === row.year} hover onClick={() => onSelectYear(item.year)} sx={{ cursor: 'pointer' }}><TableCell sx={{ fontWeight: 700 }}>{item.year}</TableCell>{(['opening_net_worth_inr','contributions_inr','investment_gain_inr','property_gain_inr','rent_received_inr','withdrawals_inr','closing_net_worth_inr'] as const).map(key => <TableCell key={key} align="right">{money(item[key].value)}</TableCell>)}<TableCell align="right">{item.investment_xirr_pct.value == null ? 'Missing' : `${item.investment_xirr_pct.value}%`}</TableCell><TableCell><Chip size="small" label={reconciliationMeta[item.reconciliation.status].label} color={reconciliationMeta[item.reconciliation.status].color} variant="outlined"/></TableCell></TableRow>)}</TableBody></Table></Box></Paper>
  </Stack>;
};

const emptyField: AnnualReviewField = { value: null, calculated_value: null, source: 'missing', explanation: 'No source data is available' };
const emptyReview = (year: number): AnnualReviewResponse => ({ year, opening_snapshot_date: null, closing_snapshot_date: null, opening_net_worth_inr: emptyField, contributions_inr: emptyField, investment_gain_inr: emptyField, property_gain_inr: emptyField, rent_received_inr: emptyField, withdrawals_inr: emptyField, closing_net_worth_inr: emptyField, investment_xirr_pct: emptyField, reconciliation: { status: 'incomplete', expected_closing_inr: null, difference_inr: null }, notes: null });

const PortfolioAnnualReview: React.FC = () => {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ['portfolio-annual-reviews'], queryFn: fetchAnnualReviews, retry: 1 });
  const [year, setYear] = React.useState(new Date().getFullYear());
  const [editorOpen, setEditorOpen] = React.useState(false);
  const [editorError, setEditorError] = React.useState<string | null>(null);
  React.useEffect(() => { if (query.data?.length && !query.data.some(item => item.year === year)) setYear(query.data[0].year); }, [query.data, year]);
  const selected = query.data?.find(item => item.year === year) ?? emptyReview(year);
  const refresh = () => client.invalidateQueries({ queryKey: ['portfolio-annual-reviews'] });
  const save = useMutation({ mutationFn: (payload: AnnualReviewOverrideUpdate) => saveAnnualReviewOverrides(year, payload), onSuccess: async () => { setEditorError(null); setEditorOpen(false); await refresh(); }, onError: () => setEditorError('Annual review changes could not be saved. Existing data is unchanged.') });
  const remove = useMutation({ mutationFn: () => deleteAnnualReviewOverrides(year), onSuccess: async () => { setEditorError(null); setEditorOpen(false); await refresh(); }, onError: () => setEditorError('Overrides could not be deleted.') });
  const addYear = () => {
    const raw = prompt('Calendar year to add', String(new Date().getFullYear()));
    if (raw == null) return;
    const next = Number(raw);
    if (!Number.isInteger(next) || next < 2000 || next > new Date().getFullYear()) { setEditorError('Enter a calendar year from 2000 through the current year.'); return; }
    setYear(next); setEditorError(null); setEditorOpen(true);
  };
  if (query.isLoading) return <Stack spacing={1}><Skeleton height={42}/><Skeleton variant="rounded" height={120}/><Skeleton variant="rounded" height={280}/></Stack>;
  if (query.isError) return <Alert severity="error" action={<Button onClick={() => query.refetch()}>Retry</Button>}>Annual Review could not be loaded. No estimates are shown.</Alert>;
  const reviews = query.data ?? [];
  if (!reviews.length) return <Paper variant="outlined" sx={{ p: 3, textAlign: 'center' }}><Typography variant="h6" fontWeight={800}>Start your annual wealth review</Typography><Typography color="text.secondary" mb={2}>No annual source data or manual review exists yet.</Typography><Button variant="contained" startIcon={<AddRoundedIcon/>} onClick={() => setEditorOpen(true)}>Add {year}</Button><AnnualReviewEditor open={editorOpen} review={selected} saving={save.isPending} error={editorError} onClose={() => setEditorOpen(false)} onSave={payload => save.mutate(payload)} onDelete={() => remove.mutate()}/></Paper>;
  return <><PortfolioAnnualReviewView reviews={reviews} selectedYear={year} onSelectYear={setYear} onAddYear={addYear} onEdit={() => setEditorOpen(true)}/><AnnualReviewEditor open={editorOpen} review={selected} saving={save.isPending || remove.isPending} error={editorError} onClose={() => setEditorOpen(false)} onSave={payload => save.mutate(payload)} onDelete={() => { if (confirm(`Delete manual overrides for ${year}?`)) remove.mutate(); }}/></>;
};

export default PortfolioAnnualReview;
