import * as React from 'react';
import {
  Drawer, List, ListItemButton, ListItemIcon, ListItemText, Toolbar, Box, Typography, Divider
} from '@mui/material';
import DashboardIcon from '@mui/icons-material/SpaceDashboard';
import ListIcon from '@mui/icons-material/ViewList';
import BookmarkIcon from '@mui/icons-material/BookmarkBorder';
import NotificationsIcon from '@mui/icons-material/Notifications';
import HistoryIcon from '@mui/icons-material/History';
import SettingsIcon from '@mui/icons-material/Settings';
import SchoolIcon from '@mui/icons-material/School';
import { NavLink } from 'react-router-dom';

export const NAV_WIDTH = 240;

const items = [
  { to: '/', label: 'Dashboard', icon: <DashboardIcon /> },
  { to: '/screener', label: 'Screener', icon: <ListIcon /> },
  { to: '/watchlist', label: 'Watchlist', icon: <BookmarkIcon /> },
  { to: '/alerts', label: 'Alerts', icon: <NotificationsIcon /> },
  { to: '/history', label: 'History', icon: <HistoryIcon /> },
  { to: '/settings', label: 'Settings', icon: <SettingsIcon /> },
  { to: '/learning', label: 'Learning', icon: <SchoolIcon /> },
];

export default function LeftNav() {
  return (
    <Drawer
      variant="permanent"
      sx={{
        width: NAV_WIDTH,
        flexShrink: 0,
        '& .MuiDrawer-paper': { width: NAV_WIDTH, boxSizing: 'border-box' },
      }}
    >
      {/* Top spacer aligned with AppBar height */}
      <Toolbar sx={{ minHeight: 64 }} />
      {/* Brand block */}
      <Box sx={{ px: 2, pb: 1 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25, mb: 1 }}>
          <Box
            sx={{
              width: 32, height: 32, borderRadius: '10px',
              display: 'grid', placeItems: 'center',
              bgcolor: 'primary.main', color: 'black', fontWeight: 800, fontSize: 14,
            }}
          >
            MS
          </Box>
          <Box>
            <Typography variant="subtitle2" sx={{ lineHeight: 1.1 }}>Momentum Suite</Typography>
            <Typography variant="caption" color="text.secondary">Scanner</Typography>
          </Box>
        </Box>
      </Box>
      <Divider />
      {/* Nav items */}
      <List sx={{ pt: 1 }}>
        {items.map((it) => (
          <ListItemButton
            key={it.to}
            component={NavLink}
            to={it.to}
            sx={{
              mx: 1,
              mb: .5,
              '&.active': { bgcolor: '#152238' },
            }}
          >
            <ListItemIcon sx={{ minWidth: 36, color: 'text.secondary' }}>{it.icon}</ListItemIcon>
            <ListItemText primary={it.label} />
          </ListItemButton>
        ))}
      </List>
    </Drawer>
  );
}
