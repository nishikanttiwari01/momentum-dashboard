// frontend/src/features/layout/LeftNav.tsx
import * as React from 'react';
import {
  Drawer, List, ListItemButton, ListItemIcon, ListItemText, Toolbar, Box, Typography, Divider
} from '@mui/material';
import DashboardIcon from '@mui/icons-material/SpaceDashboard';
import ListIcon from '@mui/icons-material/ViewList';
import BookmarkIcon from '@mui/icons-material/BookmarkBorder';
import NotificationsIcon from '@mui/icons-material/Notifications';
import ArticleIcon from '@mui/icons-material/Article';
import AccountBalanceWalletIcon from '@mui/icons-material/AccountBalanceWallet';
import HistoryIcon from '@mui/icons-material/History';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import SettingsIcon from '@mui/icons-material/Settings';
import SchoolIcon from '@mui/icons-material/School';
import { NavLink } from 'react-router-dom';

// Image placed under frontend/src/assets/
import ShubhLabhImg from '@/assets/shubh-labh-swastik-stickers.jpg';

export const NAV_WIDTH = 165;

const items = [
  { to: '/', label: 'Dashboard', icon: <DashboardIcon /> },
  { to: '/screener', label: 'Screener', icon: <ListIcon /> },
  { to: '/portfolio', label: 'Portfolio', icon: <AccountBalanceWalletIcon /> },
  { to: '/news', label: 'News', icon: <ArticleIcon /> },
  { to: '/history', label: 'Trades', icon: <TrendingUpIcon  /> }, // ← renamed
  { to: '/learning', label: 'Learning', icon: <SchoolIcon /> },
  { to: '/simulator', label: 'Simulator', icon: <BookmarkIcon /> },
  { to: '/alerts', label: 'Alerts', icon: <NotificationsIcon /> },
  { to: '/settings', label: 'Settings', icon: <SettingsIcon /> },
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
      {/* Top spacer aligned with AppBar height (adjust if your header height changes) */}
      <Toolbar sx={{ minHeight: 52 }} />

      {/* Brand block — image on top, text below */}
      <Box sx={{ px: 2, pb: 1 }}>
        <Box
          sx={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            textAlign: 'center',
            gap: 0.75,
            mb: 1,
          }}
        >
          <Box
            component="img"
            src={ShubhLabhImg}
            alt="Shubh Labh"
            sx={{
              width: 40,
              height: 40,
              borderRadius: '10px',
              objectFit: 'contain',
              bgcolor: 'common.white',
              p: 0.5,
              border: '1px solid rgba(0,0,0,0.06)',
              boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
            }}
          />
          <Typography variant="subtitle2" sx={{ lineHeight: 1.2, fontSize: 12.5 }}>
            Shree Ganeshaya<br />Namah
          </Typography>
          <Typography variant="caption" color="text.secondary">
            Subh Labh
          </Typography>
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
              mb: 0.25,
              borderRadius: '4px',
              py: 0.6,
              '&.active': {
                bgcolor: 'rgba(46,144,250,0.08)',
                '& .MuiListItemText-primary': { color: 'primary.main', fontWeight: 600 },
                '& .MuiListItemIcon-root': { color: 'primary.main' },
              },
            }}
          >
            <ListItemIcon sx={{ minWidth: 32, color: 'text.secondary', '& svg': { fontSize: 19 } }}>{it.icon}</ListItemIcon>
            <ListItemText
              primary={it.label}
              primaryTypographyProps={{ fontSize: 13, fontWeight: 500, lineHeight: 1.2 }}
            />
          </ListItemButton>
        ))}
      </List>
    </Drawer>
  );
}
