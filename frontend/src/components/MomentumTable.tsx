// src/components/MomentumTable.tsx
import * as React from 'react';
import { DataGrid, GridColDef, GridPaginationModel, GridSortModel } from '@mui/x-data-grid';
import { Box, Alert, LinearProgress, Chip } from '@mui/material'; // ADDED Chip
import { useGetApiV1Screener } from '@/lib/api/client';
import type { GetApiV1ScreenerParams } from '@/lib/api/types';
// ✅ NEW: import the new drawer
import RightDrawer from '@/features/detail/RightDrawer';

type Props = { onSelectSymbol?: (symbol: string) => void; refetchIntervalMs?: number | false; };
//const nf2 = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 });
const normalizeNumber = (v: unknown): number | null => {
  if (v === null || v === undefined) return null;
  // convert to string, trim, strip commas, currency, percent signs
  const s = String(v).trim().replace(/[,%\s₹]/g, '');
  if (s === '') return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
};

const fmtNum = (v: unknown): string => {
  const n = normalizeNumber(v);
  if (n === null) {
    // Always return a safe string
    return v === 0 ? '0' : '';
  }
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(n);
};

const fmtPct = (v: unknown): string => {
  const n0 = normalizeNumber(v);
  if (n0 === null) return '';
  const n = Math.abs(n0) <= 1 ? n0 * 100 : n0;
  return `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(n)}%`;
};

const fmtDateTime = (v: unknown) => {            // ADDED for 'as_of' column
  if (!v) return '';
  const d = new Date(String(v));
  return isNaN(d.getTime()) ? String(v) : d.toLocaleString();
  };

const strengthColor = (s?: string | null): 'success' | 'default' | 'error' | 'info' => {
  const t = (s || '').toLowerCase();
  if (t.includes('very-strong') || t.includes('strong')) return 'success';
  if (t.includes('weak')) return 'error';
  if (t.includes('moderate') || t.includes('neutral')) return 'default';
  return 'info';
};

const yesNoChip = (v: unknown) =>
  v == null
    ? null
    : v === true || String(v).toLowerCase() === 'yes'
    ? <Chip size="small" label="Yes" color="success" variant="outlined" />
    : <Chip size="small" label="No" color="default" variant="outlined" />;

const badgeColor = (c?: string | null): 'default' | 'success' | 'error' | 'warning' | 'info' => {
  switch ((c || '').toLowerCase()) {
    case 'green': return 'success';
    case 'red': return 'error';
    case 'yellow': return 'warning';
    case 'blue': return 'info';
    default: return 'default';
  }
};

export default function MomentumTable({ onSelectSymbol, refetchIntervalMs = false }: Props) {
  const [pagination, setPagination] = React.useState<GridPaginationModel>({ page: 0, pageSize: 25 });
  const [sortModel, setSortModel] = React.useState<GridSortModel>([]); // start with no sort

  // ✅ NEW: local state to control the new Right Drawer
  const [drawerOpen, setDrawerOpen] = React.useState(false);
  const [drawerSymbol, setDrawerSymbol] = React.useState<string | null>(null);
  const openDrawerFor = React.useCallback((symbol: string) => {
    setDrawerSymbol(symbol);
    setDrawerOpen(true);
  }, []);
  const closeDrawer = React.useCallback(() => {
    setDrawerOpen(false);
    setDrawerSymbol(null);
  }, []);

  const apiParams: GetApiV1ScreenerParams = {
    page: pagination.page + 1,
    page_size: pagination.pageSize,
  };
  const s0 = sortModel[0];
  if (s0?.field) {
    // only send when present (avoids 422s)
    (apiParams as any).sort_by = s0.field;
    (apiParams as any).sort_dir = s0.sort ?? 'asc';
  }

  const query = useGetApiV1Screener(apiParams, {
    axios: { baseURL: '' },              // ← key line: call /api/v1/...
    query: {
      keepPreviousData: true,
      refetchInterval: refetchIntervalMs || false,
      retry: 0,
      onError: (e) => console.error('screener error', e),
    },
  });

  const payload = query.data?.data;
  const rows = (payload as any)?.items ?? (payload as any)?.rows ?? [];
  const rowCount = (payload as any)?.total ?? rows.length;
  const getId = (r: any) => r.id ?? r.symbol ?? `${r.ticker ?? ''}-${r.symbol ?? ''}`;

  const columns = React.useMemo<GridColDef[]>(
    () => [
      { field: 'symbol', headerName: 'Symbol', minWidth: 110 },
      { field: 'name', headerName: 'Name', flex: 1, minWidth: 160 },
      { field: 'sector', headerName: 'Sector', minWidth: 140 },

      { field: 'score', headerName: 'Score', type: 'number', width: 90 },
      { field: 'last', headerName: 'Price', type: 'number' },
      { field: 'change_pct', headerName: '% Chg', type: 'number' },
      { field: 'pct_today', headerName: '% Today', width: 100, type: 'number' },

      // add remaining fields once we confirm shape
      // week change
      { field: 'wk_change', headerName: 'Δ 1W', width: 110, type: 'number' },
      { field: 'wk_change_pct', headerName: '% 1W', width: 100, type: 'number' },
            // Returns
      { field: 'ret_1m', headerName: '% 1M', width: 90, type: 'number' },
      { field: 'ret_3m', headerName: '% 3M', width: 90, type: 'number' },
      { field: 'ret_6m', headerName: '% 6M', width: 90, type: 'number' },
      { field: 'ret_12_1m', headerName: '% 12–1M', width: 110, type: 'number' },

      // Indicators
      { field: 'rsi', headerName: 'RSI', width: 80, type: 'number' },
      { field: 'adx', headerName: 'ADX', width: 80, type: 'number' },

      // Other metrics
      { field: 'pct_from_52w_high', headerName: '% from 52W H', width: 130, type: 'number' },
      { field: 'atr_pct', headerName: 'ATR %', width: 90, type: 'number' },
      { field: 'liquidity', headerName: 'Liquidity', width: 110, type: 'number' },
      { field: 'vol_spike', headerName: 'Rel Vol', width: 90, type: 'number' },

      // Decisioning
      { field: 'buy', headerName: 'Buy', width: 80, renderCell: ({ value }) => yesNoChip(value) },
      { field: 'reason', headerName: 'Reason', flex: 1.2 , minWidth: 210},

      // Meta
      { field: 'source', headerName: 'Source', minWidth: 100,  },
      { field: 'stale', headerName: 'Stale', width: 80, renderCell: ({ value }) => yesNoChip(value) },
      { field: 'run_id', headerName: 'Run ID', minWidth: 120 },
      { field: 'as_of', headerName: 'As Of', minWidth: 160, valueFormatter: ({ value }) => fmtDateTime(value) },
      { field: 'last_index', headerName: 'Last Idx', width: 100, type: 'number' },
    ],
    []
  );

  if (query.isError) {
    return <Alert severity="error" sx={{ m: 1 }}>
      Failed to load screener
    </Alert>;
  }

  return (
    <Box sx={{ height: 720, width: '100%' }}>
      <DataGrid
        rows={rows}
        getRowId={getId}
        columns={columns}
        loading={query.isLoading || query.isFetching}
        slots={{ loadingOverlay: LinearProgress }}
        paginationMode="server"
        rowCount={rowCount}
        paginationModel={pagination}
        onPaginationModelChange={setPagination}
        pageSizeOptions={[10, 25, 50, 100]}
        sortingMode="server"
        sortModel={sortModel}
        onSortModelChange={setSortModel}
        disableColumnMenu
        density="compact"
        disableRowSelectionOnClick
        // 👉 Open ONLY the new drawer (do not call parent anymore)
        onRowClick={(p) => {
          const sym = p?.row?.symbol;
          if (sym) openDrawerFor(sym);
        }}
      />

      {/* New Right Drawer controlled here */}
      <RightDrawer symbol={drawerSymbol} open={drawerOpen} onClose={closeDrawer} />
    </Box>
  );
}
