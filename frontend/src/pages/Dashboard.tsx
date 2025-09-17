// src/pages/Dashboard.tsx
import * as React from 'react';
import { useOutletContext } from 'react-router-dom';
import type { OutletCtx } from '../layouts/AppShell';
import { Paper, Stack, Typography, Divider } from '@mui/material';
import MomentumTable from '../components/MomentumTable';
import RightDrawer from '../components/RightDrawer';

export default function Dashboard() {
  const { refetchIntervalMs } = useOutletContext<OutletCtx>();
  const [symbol, setSymbol] = React.useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = React.useState(false);

  return (
    <>
      {/* No margin, full width. Only inner padding. */}
      <Paper sx={{ p: 2, width: '100%' }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
          <Typography variant="subtitle2">Screener</Typography>
          <Typography variant="caption" color="text.secondary">
            Sorted by score (desc)
          </Typography>
        </Stack>
        <Divider sx={{ mb: 1 }} />
        <MomentumTable
          onSelectSymbol={(s) => { setSymbol(s); setDrawerOpen(true); }}
          refetchIntervalMs={refetchIntervalMs}
        />
      </Paper>

      <RightDrawer symbol={symbol} open={drawerOpen} onClose={() => setDrawerOpen(false)} />
    </>
  );
}
