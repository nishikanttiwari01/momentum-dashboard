import { createTheme } from '@mui/material/styles';
import '@mui/x-data-grid/themeAugmentation';

const bgDefault = '#0b1220';
const bgPaper  = '#0f172a';
const border   = '#1e293b';
const textPri  = '#e2e8f0';
const textSec  = '#94a3b8';
const indigo   = '#6366f1';
const sky      = '#38bdf8';
const emerald  = '#10b981';
const amber    = '#f59e0b';
const rose     = '#f43f5e';

const theme = createTheme({
  palette: {
    mode: 'dark',
    primary: { main: sky },
    secondary: { main: indigo },
    success: { main: emerald },
    warning: { main: amber },
    error:   { main: rose },
    background: { default: bgDefault, paper: bgPaper },
    divider: border,
    text: { primary: textPri, secondary: textSec },
  },
  shape: { borderRadius: 14 },
  typography: {
    fontFamily: ['Inter','Segoe UI','Roboto','Helvetica Neue','Arial','Noto Sans','sans-serif'].join(','),
    h6: { fontWeight: 800, letterSpacing: .2 },
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
      styleOverrides: { root: { backgroundColor: bgPaper, border: `1px solid ${border}`, borderRadius: 16 } },
    },
    MuiAppBar: {
      defaultProps: { color: 'default' },
      styleOverrides: { root: { backgroundColor: bgDefault, borderBottom: `1px solid ${border}` } },
    },
    MuiDrawer: {
      styleOverrides: {
        paper: { backgroundColor: bgPaper, color: textPri, borderRight: `1px solid ${border}` },
      },
    },
    MuiButton: {
      defaultProps: { size: 'small' },
      styleOverrides: { root: { textTransform: 'none', fontWeight: 600, borderRadius: 10 } },
    },
    MuiChip: {
      defaultProps: { size: 'small' }, // we set variant per usage
      styleOverrides: {
        root: { borderRadius: 10 },
        filled: { fontWeight: 700 },
      },
    },
    MuiDivider: { styleOverrides: { root: { borderColor: border } } },
    MuiLinearProgress: { styleOverrides: { root: { height: 8, borderRadius: 999 } } },
    MuiDataGrid: {
      styleOverrides: {
        root: { border: `1px solid ${border}` },
        columnHeaders: { backgroundColor: '#0e1628' },
      },
    },
  },
});

export default theme;
