import React from 'react';
import { Alert, Box, Button, Chip, Divider, Drawer, Stack, TextField, Typography } from '@mui/material';
import type { AnnualReviewOverrideUpdate, AnnualReviewResponse } from './wealthTypes';

type EditableKey = Exclude<keyof AnnualReviewOverrideUpdate, never>;
type FormValues = Partial<Record<EditableKey, string>>;

const fields: { key: EditableKey; label: string; signed?: boolean; suffix?: string }[] = [
  { key: 'opening_net_worth_inr', label: 'Opening net worth' },
  { key: 'contributions_inr', label: 'Contributions' },
  { key: 'investment_gain_inr', label: 'Investment gain / loss', signed: true },
  { key: 'property_gain_inr', label: 'Property gain / loss', signed: true },
  { key: 'rent_received_inr', label: 'Rent received' },
  { key: 'withdrawals_inr', label: 'Withdrawals and goal outflows' },
  { key: 'closing_net_worth_inr', label: 'Closing net worth' },
  { key: 'investment_xirr_pct', label: 'Investment XIRR', signed: true, suffix: '%' },
];

export function buildAnnualReviewOverridePayload(values: FormValues, changed: Set<EditableKey>): AnnualReviewOverrideUpdate {
  const payload: AnnualReviewOverrideUpdate = {};
  changed.forEach(key => {
    const raw = values[key] ?? '';
    if (key === 'notes') payload.notes = raw.trim() || null;
    else payload[key] = raw === '' ? null : Number(raw);
  });
  return payload;
}

const initialValues = (review: AnnualReviewResponse): FormValues => {
  const result: FormValues = { notes: review.notes ?? '' };
  fields.forEach(({ key }) => { result[key] = review[key].value == null ? '' : String(review[key].value); });
  return result;
};

type Props = {
  open: boolean;
  review: AnnualReviewResponse;
  saving: boolean;
  error?: string | null;
  onClose: () => void;
  onSave: (payload: AnnualReviewOverrideUpdate) => void;
  onDelete: () => void;
};

const AnnualReviewEditor: React.FC<Props> = ({ open, review, saving, error, onClose, onSave, onDelete }) => {
  const [values, setValues] = React.useState<FormValues>(() => initialValues(review));
  const [changed, setChanged] = React.useState<Set<EditableKey>>(new Set());
  React.useEffect(() => { if (open) { setValues(initialValues(review)); setChanged(new Set()); } }, [open, review]);

  const update = (key: EditableKey, value: string) => {
    setValues(current => ({ ...current, [key]: value }));
    setChanged(current => new Set(current).add(key));
  };
  const invalid = fields.some(({ key, signed }) => changed.has(key) && values[key] !== '' && (!Number.isFinite(Number(values[key])) || (!signed && Number(values[key]) < 0)));

  return <Drawer anchor="right" open={open} onClose={() => !saving && onClose()} PaperProps={{ sx: { width: { xs: '100%', sm: 460 }, maxWidth: '100%' } }}>
    <Stack sx={{ p: 2.25, minHeight: '100%', boxSizing: 'border-box' }} spacing={1.5}>
      <Box><Typography variant="h6" fontWeight={850}>Edit {review.year} annual review</Typography><Typography variant="body2" color="text.secondary">Only changed fields are saved as manual overrides.</Typography></Box>
      {error ? <Alert severity="error">{error}</Alert> : null}
      <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1.25 }}>
        {fields.map(({ key, label, signed, suffix }) => {
          const field = review[key];
          return <Box key={key}>
            <TextField fullWidth size="small" type="number" label={label} value={values[key] ?? ''} onChange={event => update(key, event.target.value)} disabled={saving} error={changed.has(key) && values[key] !== '' && (!Number.isFinite(Number(values[key])) || (!signed && Number(values[key]) < 0))} InputProps={{ endAdornment: <Typography variant="caption">{suffix ?? '₹'}</Typography> }} />
            <Stack direction="row" alignItems="center" justifyContent="space-between" mt={.4}><Chip size="small" label={field.source.replace('_', ' ')} color={field.source === 'manual' ? 'warning' : field.source === 'missing' ? 'default' : 'info'} variant="outlined" sx={{ height: 20, fontSize: 10 }}/>{field.source === 'manual' ? <Button size="small" onClick={() => update(key, '')}>Restore calculated</Button> : null}</Stack>
          </Box>;
        })}
      </Box>
      <TextField label="Review notes" multiline minRows={3} value={values.notes ?? ''} onChange={event => update('notes', event.target.value)} disabled={saving}/>
      <Divider />
      <Typography variant="caption" color="text.secondary">Deleting overrides restores imported and calculated values. It never deletes portfolio transactions or snapshots.</Typography>
      <Stack direction="row" gap={1} sx={{ mt: 'auto' }}><Button variant="contained" disabled={!changed.size || invalid || saving} onClick={() => onSave(buildAnnualReviewOverridePayload(values, changed))}>{saving ? 'Saving…' : 'Save changes'}</Button><Button disabled={saving} onClick={onClose}>Cancel</Button><Button color="error" disabled={saving} onClick={onDelete} sx={{ ml: 'auto' }}>Delete overrides</Button></Stack>
    </Stack>
  </Drawer>;
};

export default AnnualReviewEditor;
