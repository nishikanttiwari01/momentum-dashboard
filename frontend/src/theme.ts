// frontend/src/theme.ts — approved design: white minimal base (Kite-inspired),
// Poppins headings + Inter body, bright data accents. No purple, no gradients.
import { createTheme, lighten, darken, alpha } from '@mui/material/styles';
import '@mui/x-data-grid/themeAugmentation';

// === Approved palette ===
const primary  = '#2E90FA'; // blue — links, active tab, selection
const secondary= '#FF5722'; // orange — brand mark, top-pick accents
const warning  = '#F79009'; // amber — watch signals
const success  = '#00B386'; // green — gains, tranche-ready
const error    = '#F04438'; // red — losses, stops
const info     = '#06AED4'; // cyan

const bgDefault = '#FFFFFF';
const bgLight   = '#FAFAFC';
const paper     = '#FFFFFF';
const divider   = '#ECECEC';
const textPri   = '#212121';
const textSec   = '#6B6B6B';
const textMut   = '#9B9B9B';

const headingFamily = ['Poppins', 'Inter', 'sans-serif'].join(',');

const theme = createTheme({
  palette: {
    mode: 'light',
    primary:  { main: primary,  light: lighten(primary, 0.075),  dark: darken(primary, 0.15) },
    secondary:{ main: secondary,light: lighten(secondary,0.075), dark: darken(secondary,0.15), contrastText:'#fff' },
    warning:  { main: warning,  light: lighten(warning, 0.075),  dark: darken(warning, 0.15) },
    success:  { main: success,  light: lighten(success, 0.075),  dark: darken(success, 0.15) },
    error:    { main: error,    light: lighten(error,   0.075),  dark: darken(error,   0.15) },
    info:     { main: info,     light: lighten(info,    0.075),  dark: darken(info,    0.15) },
    background: { default: bgDefault, paper },
    divider,
    text: { primary: textPri, secondary: textSec },
  },
  shape: { borderRadius: 6 },
  typography: {
    fontFamily: ['Inter','Segoe UI','Roboto','Helvetica Neue','Arial','sans-serif'].join(','),
    h1:{ fontSize:'2.4rem',  fontWeight:600, fontFamily: headingFamily },
    h2:{ fontSize:'1.8rem',  fontWeight:600, fontFamily: headingFamily },
    h3:{ fontSize:'1.5rem',  fontWeight:600, fontFamily: headingFamily },
    h4:{ fontSize:'1.3rem',  fontWeight:600, fontFamily: headingFamily },
    h5:{ fontSize:'1.15rem', fontWeight:600, fontFamily: headingFamily },
    h6:{ fontSize:'1rem',    fontWeight:600, fontFamily: headingFamily },
    subtitle1:{ fontWeight:600, fontFamily: headingFamily },
    subtitle2:{ fontWeight:600 },
    button:{ textTransform:'none', fontWeight:600 },
  },
  shadows: [
    'none',
    'none',
    ...Array(23).fill('0 1px 4px rgba(0,0,0,0.05)'),
  ] as any,
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: { backgroundColor: bgDefault },
        a: { color: primary, textDecoration: 'none' },
        '*::-webkit-scrollbar': { width: '8px', height: '8px' },
        '*::-webkit-scrollbar-thumb': { backgroundColor: 'rgba(0,0,0,.15)', borderRadius: 8 },
        '::selection': { background: 'rgba(46,144,250,.15)' },
      },
    },
    MuiAppBar: {
      defaultProps: { color: 'inherit', elevation: 0 },
      styleOverrides: {
        root: {
          background: '#fff',
          color: textPri,
          borderBottom: `1px solid ${divider}`,
          '& .MuiIconButton-root, & .MuiSvgIcon-root': { color: textSec },
          '& .MuiTypography-root': { color: textPri },
          '& .MuiBadge-badge': { backgroundColor: secondary, color: '#fff' },
        },
      },
    },
    MuiDrawer: {
      styleOverrides: { paper: { backgroundColor: paper, borderRight: `1px solid ${divider}` } },
    },
    MuiPaper: {
      defaultProps: { elevation: 0 },
      styleOverrides: { root: { border: `1px solid ${divider}`, borderRadius: 8 } },
    },
    MuiCard: {
      defaultProps: { elevation: 0 },
      styleOverrides: { root: { border: `1px solid ${divider}`, borderRadius: 8 } },
    },
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: { root: { borderRadius: 4, fontWeight: 600 } },
    },
    MuiChip: { styleOverrides: { root: { borderRadius: 4, fontWeight: 600 } } },
    MuiMenu: { styleOverrides: { paper: { boxShadow: '0 4px 16px rgba(0,0,0,0.08)', borderRadius: 6 } } },
    MuiSelect: { styleOverrides: { icon: { color: textMut } } },
    MuiListItem: {
      styleOverrides: {
        root: {
          '&.Mui-selected,&.Mui-selected:hover': { backgroundColor: `${bgLight} !important` },
          '&:hover,&:focus': { backgroundColor: bgLight },
        },
      },
    },
    MuiInputBase: { styleOverrides: { root: { borderRadius: 4 } } },
    MuiOutlinedInput: { styleOverrides: { root: { borderRadius: 4 } } },
    MuiTableCell: {
      styleOverrides: {
        head: {
          backgroundColor: '#fff',
          color: textMut,
          fontWeight: 500,
          fontSize: 11,
          textTransform: 'uppercase',
          letterSpacing: '0.04em',
          borderBottom: `1px solid ${divider}`,
        },
        root: { borderBottom: `1px solid #F5F5F5`, fontVariantNumeric: 'tabular-nums' },
      },
    },
    MuiDivider: { styleOverrides: { root: { borderColor: divider } } },
    MuiTooltip: {
      styleOverrides: {
        tooltip: { fontSize: 12, backgroundColor: '#fff', color: textPri, border: `1px solid ${divider}`, boxShadow: '0 4px 16px rgba(0,0,0,0.08)' },
      },
    },
    MuiToggleButton: {
      styleOverrides: {
        root: {
          borderRadius: 4,
          padding: '2px 10px',
          fontSize: 12,
          '&.Mui-selected': { backgroundColor: alpha(primary, 0.08), color: primary, fontWeight: 600 },
        },
      },
    },
    MuiDataGrid: {
      defaultProps: { density: 'compact' },
      styleOverrides: {
        root: { border: `1px solid ${divider}`, borderRadius: 8, backgroundColor: paper },
        columnHeaders: { backgroundColor: '#fff', borderBottom: `1px solid ${divider}` },
        cell: { borderBottom: `1px solid #F5F5F5` },
        row: { '&:hover': { backgroundColor: '#F7FBFF' } },
        footerContainer: { borderTop: `1px solid ${divider}` },
      },
    },
  },
});

export default theme;
