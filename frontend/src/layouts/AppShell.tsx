import * as React from 'react';
import { Box, Toolbar } from '@mui/material';
import { Outlet } from 'react-router-dom';
import AppTopBar from '@/features/layout/AppTopBar';
import LeftNav, { NAV_WIDTH } from '@/features/layout/LeftNav';

export type RefreshOpt = 'off' | '15' | '30' | '60' | 'focus';
export type OutletCtx = { refetchIntervalMs: number | false; refresh: RefreshOpt; setRefresh: (r: RefreshOpt) => void };

export default function AppShell() {
  const [refresh, setRefresh] = React.useState<RefreshOpt>('off');
  const refetchIntervalMs = React.useMemo(() => {
    if (refresh === 'off' || refresh === 'focus') return false as const;
    return Number(refresh) * 1000;
  }, [refresh]);

  return (
  <Box sx={(theme) => ({
    display: 'flex',
    minHeight: '100vh',
    backgroundColor: theme.palette.background.default,
  })}>
      <LeftNav />
      <AppTopBar refresh={refresh} setRefresh={setRefresh} navWidth={NAV_WIDTH} />

      {/* Main content area: shifted exactly by the drawer width, absolutely no extra padding */}
      <Box component="main" sx={{ flexGrow: 1, px: 0 }}>
        {/* push below AppBar */}
        <Toolbar />
        {/* Page outlet: keep it FULL width; individual pages/cards control their own padding */}
        <Box sx={{ px: 0, py: 2 }}>
          <Outlet context={{ refetchIntervalMs, refresh, setRefresh }} />
        </Box>
      </Box>
    </Box>
  );
}
