// frontend/src/features/layout/AppTopBar.tsx
// Approved design: brand + Momentum | Portfolio tabs on the left,
// auto-refresh controls on the right. No title banner.
import * as React from 'react';
import {
  AppBar, Toolbar, Box, Stack,
  FormControl, InputLabel, Select, MenuItem,
  IconButton, Typography, Tabs, Tab,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import { useLocation, useNavigate } from 'react-router-dom';

type RefreshOpt = 'off' | '15' | '30' | '60' | 'focus';

const HEADER_HEIGHT = 52;

export default function AppTopBar({
  refresh, setRefresh, navWidth,
}: { refresh: RefreshOpt; setRefresh: (r: RefreshOpt) => void; navWidth: number; }) {
  const navigate = useNavigate();
  const location = useLocation();
  const tab = location.pathname.startsWith('/portfolio') ? '/portfolio' : '/';

  return (
    <AppBar
      position="fixed"
      elevation={0}
      sx={(theme) => ({
        zIndex: theme.zIndex.drawer + 1,
        ml: 0,
        width: '100%',
        mt: 0,
        mr: 0,
        borderRadius: 0,
        color: 'text.primary',
        background: '#fff',
        borderBottom: '1px solid #ECECEC',
        boxShadow: 'none',
      })}
    >
      <Toolbar sx={{ minHeight: HEADER_HEIGHT, px: 2, gap: 2 }}>
        <Typography
          sx={{
            fontFamily: 'Poppins, Inter, sans-serif',
            fontWeight: 600,
            fontSize: 15,
            color: 'secondary.main',
            whiteSpace: 'nowrap',
            cursor: 'pointer',
          }}
          onClick={() => navigate('/')}
        >
          ◆ Momentum
        </Typography>

        <Tabs
          value={tab}
          onChange={(_, v) => navigate(v)}
          sx={{
            minHeight: HEADER_HEIGHT,
            '& .MuiTab-root': {
              minHeight: HEADER_HEIGHT,
              textTransform: 'none',
              fontFamily: 'Poppins, Inter, sans-serif',
              fontWeight: 500,
              fontSize: 13.5,
              px: 2,
            },
          }}
        >
          <Tab label="Momentum" value="/" />
          <Tab label="Portfolio" value="/portfolio" />
        </Tabs>

        <Box sx={{ flexGrow: 1 }} />

        <Stack direction="row" spacing={1} alignItems="center">
          <FormControl size="small" variant="outlined">
            <InputLabel id="auto-refresh-label">Auto refresh</InputLabel>
            <Select
              labelId="auto-refresh-label"
              label="Auto refresh"
              value={refresh}
              onChange={(e) => setRefresh(e.target.value as RefreshOpt)}
              sx={{ minWidth: 132, height: 32 }}
              MenuProps={{ MenuListProps: { dense: true } }}
            >
              <MenuItem value="off">Off</MenuItem>
              <MenuItem value="15">Every 15s</MenuItem>
              <MenuItem value="30">Every 30s</MenuItem>
              <MenuItem value="60">Every 60s</MenuItem>
              <MenuItem value="focus">Only when focused</MenuItem>
            </Select>
          </FormControl>
          <IconButton
            aria-label="refresh-now"
            title="Refresh now"
            onClick={() => window.dispatchEvent(new Event('focus'))}
            size="small"
          >
            <RefreshIcon fontSize="small" />
          </IconButton>
        </Stack>
      </Toolbar>
    </AppBar>
  );
}
