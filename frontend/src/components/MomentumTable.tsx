import * as React from 'react';
import { DataGrid, GridColDef, GridPaginationModel, GridSortModel } from '@mui/x-data-grid';
import { Box, Alert, LinearProgress } from '@mui/material';
import { useGetScreener } from '@/lib/api/client';
import type { GetScreenerParams } from '@/lib/api/types';

type Props = { onSelectSymbol?: (symbol: string) => void; refetchIntervalMs?: number | false; };
const nf2 = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 });
const normalizeNumber = (v: unknown): number | null => {
  if (v === null || v === undefined) return null;
  // convert to string, trim, strip commas, currency, percent signs
  const s = String(v).trim().replace(/[,%\s₹]/g, '');
  if (s === '') return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
};

const fmtNum = (v: unknown) => {
  const n = normalizeNumber(v);
  if (n === null) return v === 0 ? '0' : (v ?? '') as string;
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(n);
};

const fmtPct = (v: unknown) => {
  const n0 = normalizeNumber(v);
  if (n0 === null) return (v ?? '') as string;
  // tolerate 0.12 *or* 12 coming from API
  const n = Math.abs(n0) <= 1 ? n0 * 100 : n0;
  return `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(n)}%`;
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

  const apiParams: GetScreenerParams = {
    page: pagination.page + 1,
    page_size: pagination.pageSize,
  };
  const s0 = sortModel[0];
  if (s0?.field) {
    // only send when present (avoids 422s)
    (apiParams as any).sort_by = s0.field;
    (apiParams as any).sort_dir = s0.sort ?? 'asc';
  }

  const query = useGetScreener(apiParams, {
    axios: { baseURL: '/api/v1' },              // ← key line: call /api/v1/...
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
      { field: 'score', headerName: 'Score', type: 'number', width: 100 },
      { field: 'price', headerName: 'Price', type: 'number', width: 110 },
      // add remaining fields once we confirm shape
      // week change
      { field: 'wk_change', headerName: 'Δ 1W', width: 110, type: 'number', valueFormatter: ({ value }) => fmtNum(value) },
      { field: 'wk_change_pct', headerName: '% 1W', width: 100, type: 'number', valueFormatter: ({ value }) => fmtPct(value) },

      // returns
      { field: 'ret_1m', headerName: '% 1M', width: 90, type: 'number', valueFormatter: ({ value }) => fmtPct(value) },
      { field: 'ret_3m', headerName: '% 3M', width: 90, type: 'number', valueFormatter: ({ value }) => fmtPct(value) },
      { field: 'ret_6m', headerName: '% 6M', width: 90, type: 'number', valueFormatter: ({ value }) => fmtPct(value) },
      //{ field: 'ret_12_1m', headerName: '% 12-1M', width: 110, type: 'number', valueFormatter: ({ value }) => fmtPct(value) },
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
        onRowClick={(p) => onSelectSymbol?.(p.row.symbol)}
      />
    </Box>
  );
}
