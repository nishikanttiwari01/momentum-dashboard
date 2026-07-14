import * as React from 'react';
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, Stack, TextField } from '@mui/material';
import axios from 'axios';

export default function AddUsTransactionDialog({ open, onClose, onSaved }: {
  open: boolean; onClose: () => void; onSaved: () => Promise<void> | void;
}) {
  const [purchasedAt, setPurchasedAt] = React.useState(() => new Date().toISOString().slice(0, 16));
  const [quantity, setQuantity] = React.useState('');
  const [price, setPrice] = React.useState('');
  const [fees, setFees] = React.useState('0');
  const [error, setError] = React.useState('');
  const [saving, setSaving] = React.useState(false);

  const save = async () => {
    const q = Number(quantity), p = Number(price), f = Number(fees || 0);
    if (!(q > 0) || !(p > 0) || !(f >= 0)) { setError('Enter a positive quantity and price; fees cannot be negative.'); return; }
    setSaving(true); setError('');
    try {
      await axios.post('/api/v1/portfolio/us/transactions', {
        instrument_id: 'qqq', purchased_at: new Date(purchasedAt).toISOString(),
        quantity: q, price_usd: p, fees_usd: f,
      });
      await onSaved(); setQuantity(''); setPrice(''); setFees('0'); onClose();
    } catch (e: any) {
      setError(e?.response?.data?.detail?.[0]?.msg || e?.message || 'Could not save purchase.');
    } finally { setSaving(false); }
  };

  return <Dialog open={open} onClose={saving ? undefined : onClose} fullWidth maxWidth="sm">
    <DialogTitle>Add QQQ purchase</DialogTitle>
    <DialogContent><Stack spacing={2} sx={{ pt: 1 }}>
      {error && <Alert severity="error">{error}</Alert>}
      <TextField label="Purchase date and time" type="datetime-local" value={purchasedAt} onChange={e => setPurchasedAt(e.target.value)} InputLabelProps={{ shrink: true }} />
      <TextField label="Quantity" type="number" value={quantity} onChange={e => setQuantity(e.target.value)} inputProps={{ min: 0, step: 'any' }} />
      <TextField label="Price per unit (USD)" type="number" value={price} onChange={e => setPrice(e.target.value)} inputProps={{ min: 0, step: 'any' }} />
      <TextField label="Fees (USD, optional)" type="number" value={fees} onChange={e => setFees(e.target.value)} inputProps={{ min: 0, step: 'any' }} />
    </Stack></DialogContent>
    <DialogActions><Button onClick={onClose} disabled={saving}>Cancel</Button><Button variant="contained" onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save purchase'}</Button></DialogActions>
  </Dialog>;
}
