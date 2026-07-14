import * as React from 'react';
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, Stack, TextField } from '@mui/material';
import axios from 'axios';

export default function AddFundTransactionDialog({ open, fundId, fundName, onClose, onSaved }: {
  open: boolean; fundId: string; fundName: string; onClose: () => void; onSaved: () => Promise<void> | void;
}) {
  const [date, setDate] = React.useState(new Date().toISOString().slice(0, 10));
  const [amount, setAmount] = React.useState(''), [units, setUnits] = React.useState('');
  const [nav, setNav] = React.useState(''), [fees, setFees] = React.useState('0');
  const [error, setError] = React.useState(''), [saving, setSaving] = React.useState(false);
  const save = async () => {
    const n = Number(nav), a = amount ? Number(amount) : undefined, u = units ? Number(units) : undefined, f = Number(fees || 0);
    if (!(n > 0) || (!a && !u) || !(f >= 0)) { setError('Enter NAV and either a positive amount or units.'); return; }
    setSaving(true); setError('');
    try {
      await axios.post('/api/v1/portfolio/transactions', { instrument_id: fundId, date, amount: a, units: u, nav: n, fees: f });
      await onSaved(); setAmount(''); setUnits(''); setNav(''); setFees('0'); onClose();
    } catch (e: any) { setError(e?.response?.data?.detail || e?.message || 'Could not save purchase.'); }
    finally { setSaving(false); }
  };
  return <Dialog open={open} onClose={saving ? undefined : onClose} fullWidth maxWidth="sm">
    <DialogTitle>Add {fundName} purchase</DialogTitle><DialogContent><Stack spacing={2} sx={{ pt: 1 }}>
      {error && <Alert severity="error">{String(error)}</Alert>}
      <TextField label="Purchase date" type="date" value={date} onChange={e => setDate(e.target.value)} InputLabelProps={{ shrink: true }} />
      <TextField label="Amount invested (INR)" type="number" value={amount} onChange={e => setAmount(e.target.value)} />
      <TextField label="Units (optional if amount entered)" type="number" value={units} onChange={e => setUnits(e.target.value)} />
      <TextField label="Purchase NAV" type="number" value={nav} onChange={e => setNav(e.target.value)} />
      <TextField label="Fees (INR, optional)" type="number" value={fees} onChange={e => setFees(e.target.value)} />
    </Stack></DialogContent><DialogActions><Button onClick={onClose}>Cancel</Button><Button variant="contained" disabled={saving} onClick={save}>{saving ? 'Saving…' : 'Save purchase'}</Button></DialogActions>
  </Dialog>;
}
