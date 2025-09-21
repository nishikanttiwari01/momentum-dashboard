// frontend/src/theme.ts  (full replacement)
import { createTheme, lighten, darken, alpha } from '@mui/material/styles';
import '@mui/x-data-grid/themeAugmentation';

// === Palette (from master template default) ===
const primary  = '#536DFE';
const secondary= '#FF5C93';
const warning  = '#FFC260';
const success  = '#3CD4A0';
const info     = '#9013FE';

const bgDefault = '#F6F7FF';
const bgLight   = '#F3F5FF';
const paper     = '#FFFFFF';
const divider   = '#E8EAFC';
const textPri   = '#1F2937';
const textSec   = '#6B7280';

const theme = createTheme({
  palette: {
    mode: 'light',
    primary:  { main: primary,  light: lighten(primary, 0.075),  dark: darken(primary, 0.15) },
    secondary:{ main: secondary,light: lighten(secondary,0.075), dark: darken(secondary,0.15), contrastText:'#fff' },
    warning:  { main: warning,  light: lighten(warning, 0.075),  dark: darken(warning, 0.15) },
    success:  { main: success,  light: lighten(success, 0.075),  dark: darken(success, 0.15) },
    info:     { main: info,     light: lighten(info,    0.075),  dark: darken(info,    0.15) },
    background: { default: bgDefault, paper },
    divider,
    text: { primary: textPri, secondary: textSec },
  },
  shape: { borderRadius: 14 },
  typography: {
    fontFamily: ['Inter','Segoe UI','Roboto','Helvetica Neue','Arial','Noto Sans','sans-serif'].join(','),
    h1:{ fontSize:'3rem',   fontWeight:800 },
    h2:{ fontSize:'2rem',   fontWeight:800 },
    h3:{ fontSize:'1.64rem',fontWeight:800 },
    h4:{ fontSize:'1.5rem', fontWeight:800 },
    h5:{ fontSize:'1.285rem',fontWeight:800 },
    h6:{ fontSize:'1.142rem',fontWeight:800 },
    button:{ textTransform:'none', fontWeight:700 },
  },
  // softer admin-like shadows
  shadows: [
    'none',
    '0px 3px 11px 0px #E8EAFC, 0 3px 3px -2px #B2B2B21A, 0 1px 8px 0 #9A9A9A1A',
    ...Array(22).fill('0px 3px 11px 0px #E8EAFC, 0 3px 3px -2px #B2B2B21A, 0 1px 8px 0 #9A9A9A1A'),
  ] as any,
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: { backgroundColor: bgDefault },
        a: { color: primary, textDecoration: 'none' },
        '*::-webkit-scrollbar': { width: '8px', height: '8px' },
        '*::-webkit-scrollbar-thumb': { backgroundColor: 'rgba(0,0,0,.15)', borderRadius: 8 },
        '::selection': { background: 'rgba(83,109,254,.18)' },
      },
    },
    MuiAppBar: {
  // use the theme's primary color instead of default/white
  defaultProps: { color: 'primary', elevation: 0 },
  styleOverrides: {
    root: {
      // Solid color OR keep the gradient — pick one:
      // backgroundColor: '#536DFE',
      background: 'linear-gradient(90deg, #d953feff 0%, #d13dfeff 60%, #7C4DFF 100%)',
      color: '#fff',
      borderBottom: `1px solid ${alpha('#000', 0.06)}`,
      // make everything inside the appbar white for contrast
      '& .MuiIconButton-root, & .MuiSvgIcon-root, & .MuiButton-root, & .MuiTypography-root': {
        color: '#fff',
      },
      '& .MuiBadge-badge': { backgroundColor: '#fff', color: '#ea60a0ff' },
      '& .MuiInputBase-input': { color: '#fff' },
      '& .MuiOutlinedInput-notchedOutline': { borderColor: alpha('#fff', 0.2) },
    },
  },
},
    MuiDrawer: {
      styleOverrides: { paper: { backgroundColor: paper, borderRight: `1px solid ${divider}` } },
    },
    MuiPaper: {
      defaultProps: { elevation: 1 },
      styleOverrides: { root: { border: `1px solid ${divider}`, borderRadius: 16 } },
    },
    MuiCard: {
      defaultProps: { elevation: 1 },
      styleOverrides: { root: { border: `1px solid ${divider}`, borderRadius: 16 } },
    },
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: { root: { borderRadius: 12, fontWeight: 700 } },
    },
    MuiChip: { styleOverrides: { root: { borderRadius: 10, fontWeight: 700 } } },
    MuiMenu: { styleOverrides: { paper: { boxShadow: '0px 3px 11px 0px #E8EAFC, 0 3px 3px -2px #B2B2B21A, 0 1px 8px 0 #9A9A9A1A', borderRadius: 12 } } },
    MuiSelect: { styleOverrides: { icon: { color: '#B9B9B9' } } },
    MuiListItem: {
      styleOverrides: {
        root: {
          '&.Mui-selected,&.Mui-selected:hover': { backgroundColor: `${bgLight} !important` },
          '&:hover,&:focus': { backgroundColor: bgLight },
        },
      },
    },
    MuiTouchRipple: { styleOverrides: { child: { backgroundColor: '#fff' } } },
    MuiInputBase: { styleOverrides: { root: { borderRadius: 10 } } },
    MuiOutlinedInput: { styleOverrides: { root: { borderRadius: 10 } } },
    MuiTableCell: {
      styleOverrides: {
        head: { backgroundColor: bgLight, color: textPri, fontWeight: 700 },
        root: { borderBottom: `1px solid ${divider}` },
      },
    },
    MuiDivider: { styleOverrides: { root: { borderColor: divider } } },
    MuiTooltip: { styleOverrides: { tooltip: { fontSize: 12, border: `1px solid ${divider}` } } },
    // DataGrid – match polished admin look
    MuiDataGrid: {
      defaultProps: { density: 'compact' },
      styleOverrides: {
        root: { border: `1px solid ${divider}`, borderRadius: 16, backgroundColor: paper },
        columnHeaders: { backgroundColor: bgLight, borderBottom: `1px solid ${divider}` },
        cell: { borderBottom: `1px solid ${divider}` },
        row: {
          '&:hover': { backgroundColor: '#F6F8FF' },
          '&:nth-of-type(odd)': { backgroundColor: '#FBFCFF' },
        },
        footerContainer: { borderTop: `1px solid ${divider}` },
      },
    },
  },
});

export default theme;
