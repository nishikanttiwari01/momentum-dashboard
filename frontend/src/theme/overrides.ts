// src/theme/overrides.ts
import { Components, Theme } from '@mui/material/styles';

export const componentOverrides = (theme: Theme): Components => ({
  MuiCssBaseline:{
    styleOverrides:{
      body:{ backgroundColor: theme.palette.background.default },
      a:{ color: theme.palette.primary.main, textDecoration:'none' },
    }
  },
  MuiAppBar:{
    styleOverrides:{
      root:{
        backgroundColor: theme.palette.mode==='dark' ? '#0f1117' : '#ffffff',
        color: theme.palette.text.primary,
        borderBottom:`1px solid ${theme.palette.divider}`,
        boxShadow:'none'
      }
    }
  },
  MuiDrawer:{
    styleOverrides:{
      paper:{
        backgroundColor: theme.palette.mode==='dark' ? '#0f141f' : '#ffffff',
        borderRight:`1px solid ${theme.palette.divider}`
      }
    }
  },
  MuiPaper:{
    defaultProps:{ elevation:0 },
    styleOverrides:{
      root:{
        border:`1px solid ${theme.palette.divider}`,
        borderRadius:16,
        boxShadow: theme.palette.mode==='dark'
          ? '0 1px 2px rgba(0,0,0,.35),0 4px 10px rgba(0,0,0,.25)'
          : '0 1px 2px rgba(0,0,0,.06),0 4px 10px rgba(0,0,0,.05)',
      }
    }
  },
  MuiCard:{
    defaultProps:{ elevation:0 },
    styleOverrides:{ root:{ border:`1px solid ${theme.palette.divider}`, borderRadius:16 } }
  },
  MuiButton:{
    defaultProps:{ disableElevation:true },
    styleOverrides:{ root:{ borderRadius:12, fontWeight:700 } }
  },
  MuiChip:{
    styleOverrides:{ root:{ borderRadius:10, fontWeight:700 } }
  },
  MuiMenu:{ styleOverrides:{ paper:{ border:`1px solid ${theme.palette.divider}`, borderRadius:12 } } },
  MuiTooltip:{ styleOverrides:{ tooltip:{ fontSize:12, border:`1px solid ${theme.palette.divider}` } } },
  MuiInputBase:{ styleOverrides:{ root:{ borderRadius:10 } } },
  MuiSelect:{ styleOverrides:{ outlined:{ borderRadius:10 }, icon:{ color:'#76767B' } } },
  MuiTableRow:{ styleOverrides:{ root:{ height:56 } } },
  MuiTableCell:{
    styleOverrides:{
      root:{ borderBottom:`1px solid ${theme.palette.divider}` },
      head:{
        fontWeight:700, color: theme.palette.text.primary,
        backgroundColor: theme.palette.mode==='dark' ? '#0f1320' : '#fafbff'
      }
    }
  },
  // DataGrid (x-data-grid)
  MuiDataGrid:{
    defaultProps:{ density:'compact' },
    styleOverrides:{
      root:{
        border:`1px solid ${theme.palette.divider}`,
        borderRadius:16,
        backgroundColor: theme.palette.background.paper,
      },
      columnHeaders:{
        backgroundColor: theme.palette.mode==='dark' ? '#0f1320' : '#fafbff',
        borderBottom:`1px solid ${theme.palette.divider}`,
      },
      cell:{ borderBottom:`1px solid ${theme.palette.divider}` },
      row:{
        '&:hover':{ backgroundColor: theme.palette.mode==='dark' ? '#121a2b' : '#f6f8ff' },
        '&:nth-of-type(odd)':{ backgroundColor: theme.palette.mode==='dark' ? '#0e1628' : '#fbfcff' },
      },
      footerContainer:{ borderTop:`1px solid ${theme.palette.divider}` },
    }
  },
});
