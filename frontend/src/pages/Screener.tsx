import * as React from 'react';
import { useOutletContext } from 'react-router-dom';
import type { OutletCtx } from '../layouts/AppShell';
import { Box, Button, Divider, Paper, Stack, TextField, Typography } from '@mui/material';
import MomentumTable from '../components/MomentumTable';

export default function Screener() {
  const { refetchIntervalMs } = useOutletContext<OutletCtx>();
  const [tickerInput, setTickerInput] = React.useState('');
  const [symbolFilter, setSymbolFilter] = React.useState<string | undefined>(undefined);

  const handleSubmit = React.useCallback((event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const value = tickerInput.trim();
    if (!value) {
      setSymbolFilter(undefined);
      setTickerInput('');
      return;
    }
    const normalized = value.toUpperCase();
    setSymbolFilter(normalized);
    setTickerInput(normalized);
  }, [tickerInput]);

  const handleClear = React.useCallback(() => {
    setTickerInput('');
    setSymbolFilter(undefined);
  }, []);

  return (
    <Paper sx={{ p: 2, width: '100%', display: 'flex', flexDirection: 'column', gap: 1 }}>
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        alignItems={{ xs: 'flex-start', sm: 'center' }}
        justifyContent="space-between"
        spacing={1}
        sx={{ mb: 1 }}
      >
        <Stack spacing={0.25}>
          <Typography variant="subtitle2">Full Screener</Typography>
          <Typography variant="caption" color="text.secondary">
            Filter, sort, and explore the full universe
          </Typography>
        </Stack>
        <Stack
          component="form"
          direction={{ xs: 'column', sm: 'row' }}
          spacing={1}
          alignItems={{ xs: 'stretch', sm: 'center' }}
          onSubmit={handleSubmit}
        >
          <TextField
            size="small"
            label="Ticker"
            placeholder="e.g. SUMEETINDS.NS"
            value={tickerInput}
            onChange={(event) => setTickerInput(event.target.value)}
            autoComplete="off"
            sx={{ minWidth: { xs: '100%', sm: 220 } }}
          />
          <Button type="submit" variant="contained" size="small">
            Search
          </Button>
          {(tickerInput || symbolFilter) ? (
            <Button type="button" variant="outlined" size="small" onClick={handleClear}>
              Clear
            </Button>
          ) : null}
        </Stack>
      </Stack>
      <Divider sx={{ mb: 1 }} />
      <Box sx={{ width: '100%'}}>
        <MomentumTable
          refetchIntervalMs={refetchIntervalMs}
          symbolFilter={symbolFilter}
        />
      </Box>
    </Paper>
  );
}
