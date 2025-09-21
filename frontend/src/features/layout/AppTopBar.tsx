import * as React from 'react';
import { AppBar, Toolbar, Box, Stack, FormControl, InputLabel, Select, MenuItem, IconButton,Typography } from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';

type RefreshOpt = 'off' | '15' | '30' | '60' | 'focus';

export default function AppTopBar({
  refresh, setRefresh, navWidth,
}: { refresh: RefreshOpt; setRefresh: (r: RefreshOpt) => void; navWidth: number; }) {
  return (
    <AppBar
      position="fixed"
      elevation={0}
      sx={(theme) => ({
        zIndex: theme.zIndex.drawer + 1,
        ml: `${navWidth}px`,
        width: `calc(100% - ${navWidth}px)`,
      })}
    >
      <Toolbar sx={{ minHeight: 64 }}>
        {/* No title here – brand lives in the left nav */}
        <Box sx={{ flex: 1 }}/>
         <Typography variant="subtitle2" sx={{ lineHeight: 1.1 } }>Momentum Suite    </Typography>
        
        <Stack direction="row" spacing={2} alignItems="center">
          <FormControl size="small" sx={{ minWidth: 160 }}>
            <InputLabel id="refresh-label">Auto refresh</InputLabel>
            <Select
              labelId="refresh-label"
              label="Auto refresh"
              value={refresh}
              onChange={(e) => setRefresh(e.target.value as RefreshOpt)}
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
            onClick={() => window.dispatchEvent(new Event('focus'))}
            title="Refresh now"
          >
            <RefreshIcon fontSize="small" />
          </IconButton>
        </Stack>
      </Toolbar>
    </AppBar>
  );
}
