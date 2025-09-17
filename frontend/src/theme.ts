import { createTheme } from '@mui/material/styles';
import '@mui/x-data-grid/themeAugmentation';  // <-- add this line FIRST


const bgDefault = '#0b1220';   // page background
const bgPaper  = '#0f172a';    // surfaces/cards
const border   = '#1e293b';    // border/divider
const textPri  = '#e2e8f0';
const textSec  = '#94a3b8';
const indigo   = '#6366f1';
const sky      = '#38bdf8';

const theme = createTheme({
  palette: {
    mode: 'dark',
    primary: { main: sky },
    secondary: { main: indigo },
    background: { default: bgDefault, paper: bgPaper },
    divider: border,
    text: { primary: textPri, secondary: textSec },
  },
  shape: { borderRadius: 12 },
  typography: {
    fontFamily: ['Inter','Segoe UI','Roboto','Helvetica Neue','Arial','Noto Sans','sans-serif'].join(','),
    h6: { fontWeight: 700, letterSpacing: .2 },
    subtitle2: { fontWeight: 700, letterSpacing: .2 },
    body2: { fontSize: 13.5 },
    caption: { fontSize: 12 },
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        'html, body, #root': { height: '100%' },
        body: { backgroundColor: bgDefault },
      },
    },
    MuiPaper: {
      defaultProps: { elevation: 0 },
      styleOverrides: {
        root: {
          backgroundColor: bgPaper,
          border: `1px solid ${border}`,
          borderRadius: 16,
        },
      },
    },
    MuiAppBar: {
      defaultProps: { color: 'default' },
      styleOverrides: {
        root: {
          backgroundColor: bgDefault,
          borderBottom: `1px solid ${border}`,
        },
      },
    },
    MuiDrawer: {
      styleOverrides: {
        paper: {
          backgroundColor: bgPaper,
          color: textPri,
          borderRight: `1px solid ${border}`,
        },
      },
    },
    MuiListItemButton: {
      styleOverrides: {
        root: {
          borderRadius: 10,
          margin: '2px 8px',
          '&.active': { backgroundColor: '#152238' },
          '&:hover': { backgroundColor: '#132035' },
        },
      },
    },
    MuiButton: {
      defaultProps: { size: 'small' },
      styleOverrides: {
        root: { textTransform: 'none', fontWeight: 600, borderRadius: 10 },
      },
    },
    MuiChip: {
      defaultProps: { size: 'small', variant: 'outlined' },
      styleOverrides: {
        root: { borderRadius: 8, borderColor: border, color: textPri },
      },
    },
    MuiDivider: { styleOverrides: { root: { borderColor: border } } },
  },
});

export default theme;
