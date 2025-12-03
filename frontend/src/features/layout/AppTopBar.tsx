// frontend/src/features/layout/AppTopBar.tsx
import * as React from 'react';
import {
  AppBar, Toolbar, Box, Stack,
  FormControl, InputLabel, Select, MenuItem,
  IconButton, Typography
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';

type RefreshOpt = 'off' | '15' | '30' | '60' | 'focus';

const HEADER_HEIGHT = 52; // room for primary + secondary lines

export default function AppTopBar({
  refresh, setRefresh, navWidth,
}: { refresh: RefreshOpt; setRefresh: (r: RefreshOpt) => void; navWidth: number; }) {
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
        color: 'common.white',
        background: 'linear-gradient(135deg,#6D28D9 0%,#7C3AED 40%,#8B5CF6 100%)',
        boxShadow: '0 6px 18px rgba(124,58,237,0.18)',
      })}
    >
      <Toolbar sx={{ minHeight: HEADER_HEIGHT, px: 2, position: 'relative' }}>
        {/* Centered title block (clicks pass through so controls remain interactive) */}
        <Box
          sx={{
            position: 'absolute',
            left: '50%',
            top: '50%',
            transform: 'translate(-50%, -50%)',
            textAlign: 'center',
            px: 1,
            pointerEvents: 'none',
          }}
        >
          <Typography
            variant="subtitle1"
            sx={{
              fontWeight: 900,
              letterSpacing: 0.4,
              lineHeight: 1,
              textShadow: '0 1px 0 rgba(0,0,0,0.25)',
            }}
          >
            Indian Stock Momentum Screener
          </Typography>

          <Typography
            variant="caption"
            sx={{
              display: 'block',
              mt: 0.25,
              opacity: 0.95,
              fontWeight: 600,
              textShadow: '0 1px 0 rgba(0,0,0,0.18)',
              whiteSpace: 'nowrap',
            }}
          >
            Concept by Fingrow Solutions - Powered by Vermilion Tech Craft
          </Typography>
        </Box>

        {/* Right-side controls */}
        <Stack direction="row" spacing={1} sx={{ ml: 'auto' }} alignItems="center">
          <FormControl size="small" variant="outlined">
            <InputLabel id="auto-refresh-label" sx={{ color: 'common.white' }}>Auto refresh</InputLabel>
            <Select
              labelId="auto-refresh-label"
              label="Auto refresh"
              value={refresh}
              onChange={(e) => setRefresh(e.target.value as RefreshOpt)}
              sx={{
                color: 'common.white',
                minWidth: 132,
                '.MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255,255,255,0.28)' },
                '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255,255,255,0.45)' },
                '.MuiSvgIcon-root': { color: 'inherit' },
                height: 32,
              }}
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
            sx={{ color: 'common.white' }}
            size="small"
          >
            <RefreshIcon fontSize="small" />
          </IconButton>
        </Stack>
      </Toolbar>
    </AppBar>
  );
}
