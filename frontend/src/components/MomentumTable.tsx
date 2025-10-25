// src/components/MomentumTable.tsx
import * as React from 'react';
import {
  DataGrid,
  GridColDef,
  GridPaginationModel,
  GridRenderCellParams,
  GridSortModel,
  GridLoadingOverlayProps,
  GridOverlay,
} from '@mui/x-data-grid';
import { Box, Alert, LinearProgress, Tooltip, Chip, alpha } from '@mui/material';
import { useGetApiV1Screener } from '@/lib/api/client';
import type { GetApiV1ScreenerParams } from '@/lib/api/types';
import RightDrawer from '@/features/detail/RightDrawer';


interface MomentumTableProps {
  refetchIntervalMs?: number | false;
  onSelectSymbol?: (symbol: string) => void;
  symbolFilter?: string;
  height?: number | string;
  runId?: string;
  asOf?: string;
}
const MAX_PAGE_SIZE = 100; // MUI X MIT cap

// ---------- helpers ----------
const normalizeNumber = (v: unknown): number | null => {
  if (v === null || v === undefined) return null;
  const s = String(v).trim().replace(/[₹,%\s]/g, '');
  if (!s) return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
};
const fmtNum = (v: unknown): string => {
  const n = normalizeNumber(v);
  if (n === null) return '—';
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(n);
};
const fmtPct = (v: unknown): string => {
  const n0 = normalizeNumber(v);
  if (n0 === null) return '—';
  const n = Math.abs(n0) <= 1 ? n0 * 100 : n0;
  return `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(n)}%`;
};
const signClass = (v: unknown) => {
  const n = normalizeNumber(v);
  return n == null ? '' : n < 0 ? 'text-neg' : n > 0 ? 'text-pos' : '';
};

// ---------- combined Price + %Today cell ----------
const PriceDeltaCell = (params: GridRenderCellParams) => {
  const last = normalizeNumber(params?.row?.last);
  const pctRaw = normalizeNumber(params?.row?.pct_today);
  const pctAsRatio = pctRaw == null ? null : Math.abs(pctRaw) <= 1 ? pctRaw : pctRaw / 100;
  const absChange = last != null && pctAsRatio != null ? last * pctAsRatio : null;

  const priceStr = fmtNum(last);
  const pctStr = pctRaw == null ? '' : fmtPct(pctRaw);
  const changeStr = absChange == null ? '' : fmtNum(absChange);
  const pos = (pctRaw ?? 0) >= 0;
  const colorClass = pctRaw == null ? '' : pos ? 'text-pos' : 'text-neg';
  const sign = pctRaw == null ? '' : pos ? '+' : '';

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', lineHeight: 1.2, py: 0.5 }}>
      <span>{priceStr}</span>
      {pctRaw != null && (
        <span className={colorClass} style={{ fontSize: 12 }}>
          {sign}
          {changeStr}
          {changeStr ? ' ' : ''}
          {pctStr ? `(${pctStr})` : ''}
        </span>
      )}
    </Box>
  );
};

type Badge = { label: string; category: 'BREAKOUT' | 'MOMENTUM' | 'WATCH' | 'IGNORE' | 'ACTION' };

const normalizeBadges = (row: any): Badge[] => {
  const raw = Array.isArray(row?.badges) ? row.badges : [];
  const allowed = new Set(['BREAKOUT', 'MOMENTUM', 'WATCH', 'IGNORE']);
  return raw
    .map((b: any) => ({
      label: String(b?.label ?? '').trim(),
      category: String(b?.category ?? '').toUpperCase() as Badge['category'],
    }))
    .filter((b: Badge) => b.label && allowed.has(b.category));
};

const chipSx = (cat: Badge['category']) => (theme: any) => {
  const base = {
    fontWeight: 700,
    height: 22,
    borderWidth: 1,
    '& .MuiChip-label': { px: 1, whiteSpace: 'nowrap' },
  } as const;

  switch (cat) {
    case 'MOMENTUM': {
      const c = '#7C4DFF';
      return { ...base, color: c, borderColor: alpha(c, 0.35), bgcolor: alpha(c, 0.1) };
    }
    case 'BREAKOUT': {
      const c = theme.palette.success.main;
      return { ...base, color: c, borderColor: alpha(c, 0.35), bgcolor: alpha(c, 0.1) };
    }
    case 'WATCH': {
      const c = theme.palette.info.main;
      return { ...base, color: c, borderColor: alpha(c, 0.35), bgcolor: alpha(c, 0.1) };
    }
    case 'IGNORE': {
      const c = theme.palette.text.secondary;
      return { ...base, color: c, borderColor: alpha(c, 0.25), bgcolor: alpha(c, 0.08) };
    }
    default:
      return base;
  }
};

const BADGE_ORDER: Badge['category'][] = ['ACTION', 'BREAKOUT', 'MOMENTUM', 'WATCH', 'IGNORE'];

const BadgesCell = (params: any) => {
  const badges = normalizeBadges(params?.row).sort(
    (a, b) => BADGE_ORDER.indexOf(a.category) - BADGE_ORDER.indexOf(b.category),
  );

  const max = 2;
  const shown = badges.slice(0, max);
  const extra = badges.length - shown.length;

  return (
    <Box sx={{ display: 'flex', gap: 0.5, overflow: 'hidden' }}>
      {shown.map((b, i) => (
        <Chip key={`${b.category}-${i}`} size="small" label={b.label} variant="outlined" sx={chipSx(b.category)} />
      ))}
      {extra > 0 && (
        <Tooltip title={badges.slice(max).map((b) => b.label).join(', ')}>
          <Chip size="small" label={`+${extra}`} variant="outlined" sx={{ height: 22, fontWeight: 700 }} />
        </Tooltip>
      )}
    </Box>
  );
};

const makePeriodCell =
  (absKey?: string, pctKey?: string) =>
  (params: GridRenderCellParams) => {
    const last = normalizeNumber(params?.row?.last);

    const absRaw = absKey ? normalizeNumber(params?.row?.[absKey as any]) : null;
    const pctRaw = pctKey ? normalizeNumber(params?.row?.[pctKey as any]) : null;

    const pctDec = pctRaw == null ? null : Math.abs(pctRaw) <= 1 ? pctRaw : pctRaw / 100;

    let prior: number | null = null;
    let deltaAbs: number | null = null;

    if (last != null) {
      if (absRaw != null) {
        deltaAbs = absRaw;
        prior = last - deltaAbs;
      } else if (pctDec != null && isFinite(pctDec) && pctDec > -0.9999) {
        prior = last / (1 + pctDec);
        deltaAbs = last - prior;
      }
    }

    const pos = (pctRaw ?? deltaAbs ?? 0) >= 0;
    const sign = pos ? '+' : '';
    const colorClass = pos ? 'text-pos' : 'text-neg';

    const priorStr =
      prior == null ? '—' : new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(prior);
    const absStr =
      deltaAbs == null ? '' : new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(deltaAbs);
    const pctStr = pctRaw == null ? '' : fmtPct(pctRaw);

    return (
      <Box sx={{ display: 'flex', flexDirection: 'column', lineHeight: 1.2, py: 0.5 }}>
        <span>{priorStr}</span>
        {(absStr || pctStr) && (
          <span className={colorClass} style={{ fontSize: 12 }}>
            {sign}
            {absStr}
            {absStr ? ' ' : ''}
            {pctStr ? `(${pctStr})` : ''}
          </span>
        )}
      </Box>
    );
  };

const fmtMillions = (v: unknown): string => {
  const n = normalizeNumber(v);
  if (n === null) return '—';
  const m = n / 1_000_000;
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(m) + 'M';
};
const renderMillions = (p: any) => <span>{fmtMillions(p?.value)}</span>;

// Custom loading overlay
function LinearLoadingOverlay(_: GridLoadingOverlayProps) {
  return (
    <GridOverlay>
      <Box sx={{ position: 'absolute', top: 0, left: 0, right: 0 }}>
        <LinearProgress />
      </Box>
    </GridOverlay>
  );
}

const num = (v: any): number | null => {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

export default function MomentumTable({ refetchIntervalMs = false, onSelectSymbol, symbolFilter, height, runId, asOf }: MomentumTableProps) {
  const [pagination, setPagination] = React.useState<GridPaginationModel>({ page: 0, pageSize: 25 });
  const [sortModel, setSortModel] = React.useState<GridSortModel>([]);

  // Drawer
  const [drawerOpen, setDrawerOpen] = React.useState(false);
  const [drawerSymbol, setDrawerSymbol] = React.useState<string | null>(null);
  const openDrawerFor = React.useCallback(
    (symbol: string) => {
      if (onSelectSymbol) {
        onSelectSymbol(symbol);
      }
      setDrawerSymbol(symbol);
      setDrawerOpen(true);
    },
    [onSelectSymbol],
  );
  const closeDrawer = React.useCallback(() => {
    setDrawerOpen(false);
    setDrawerSymbol(null);
  }, []);

  // --- query params (memoized) ---
  const apiParams: GetApiV1ScreenerParams = React.useMemo(() => {
    const size = Math.min(MAX_PAGE_SIZE, Math.max(1, pagination.pageSize));
    const p: GetApiV1ScreenerParams = {
      page: pagination.page + 1, // 1-based
      per_page: size,
      // also send common synonyms in case backend expects them
      // @ts-expect-error
      page_size: size,
      // @ts-expect-error
      limit: size,
      // @ts-expect-error
      offset: pagination.page * size,
    };
    const s0 = sortModel[0];
    if (s0?.field) {
      (p as any).sort_by = s0.field;
      (p as any).sort_dir = s0.sort ?? 'asc';
      (p as any).sort = s0.field;
      (p as any).order = s0.sort ?? 'asc';
      (p as any).ordering = `${s0.sort === 'desc' ? '-' : ''}${s0.field}`;
    }
    const sym = symbolFilter?.trim();
    if (sym) {
      p.symbol = sym.toUpperCase();
    }
    if (runId) {
      (p as any).run_id = runId;
    } else if (asOf) {
      (p as any).as_of = asOf;
    }
    return p;
  }, [asOf, pagination.page, pagination.pageSize, runId, sortModel, symbolFilter]);

  React.useEffect(() => {
    setPagination((prev) => (prev.page === 0 ? prev : { ...prev, page: 0 }));
  }, [symbolFilter, runId, asOf]);

  const query = useGetApiV1Screener(apiParams, {
    axios: { baseURL: '' },
    query: {
      placeholderData: (prev) => prev, // React Query v5
      refetchInterval: refetchIntervalMs || false,
      retry: 0,
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
    },
  });

  // rows + totals
  const axiosResp = query.data; // AxiosResponse | undefined
  const payload = axiosResp?.data as any;

  const rows: any[] =
    payload?.items ??
    payload?.rows ??
    payload?.data ??
    payload?.results ??
    payload?.records ??
    [];

  // Try headers first (CORS needs Access-Control-Expose-Headers server-side)
  const h = axiosResp?.headers ?? {};
  const headerTotal =
    num(h['x-total-count']) ??
    num(h['x-total']) ??
    num(h['x-total-records']) ??
    num(h['x-count']) ??
    null;

  // Then typical payload shapes
  const serverTotalRaw =
    payload?.pagination?.total ??
    payload?.pagination?.count ??
    payload?.pagination?.records ??
    payload?.pagination?.recordsTotal ??
    payload?.total ??
    payload?.count ??
    payload?.records ??
    null;
  const serverTotal = num(serverTotalRaw);

  // ----- Compute effective rowCount (with override if total looks wrong) -----
  const size = Math.min(MAX_PAGE_SIZE, Math.max(1, pagination.pageSize));
  const base = pagination.page * size;

  // start from server/header total if available
  let rowCount: number | null = headerTotal ?? serverTotal ?? null;

  // If no total, go optimistic: if we got a full page, pretend there's at least one more
  if (rowCount == null) {
    rowCount = base + rows.length + (rows.length === size ? 1 : 0);
  } else {
    // If backend says total <= items we've already shown but we still got a full page,
    // the "total" is likely the page length, not real total → override to enable Next.
    if (rows.length === size && rowCount <= base + rows.length) {
      rowCount = base + rows.length + 1;
    }
  }

  // Optional debug
  // console.debug('pagination', { asked: apiParams, page: pagination.page, size, rows: rows.length, headerTotal, serverTotal: serverTotalRaw, rowCount });

  const getId = (r: any) => r.id ?? r.symbol ?? `${r.ticker ?? ''}-${r.symbol ?? ''}`;

  const renderNum = (p: any) => <span>{fmtNum(p?.value)}</span>;
  const renderPctCell = (p: any) => <span className={signClass(p?.value)}>{fmtPct(p?.value)}</span>;

  const columns: GridColDef[] = React.useMemo(
    () => [
      { field: 'symbol', headerName: 'Ticker', minWidth: 145 },

      { field: 'score', headerName: 'Score', width: 70, type: 'number', renderCell: renderNum, cellClassName: (p) => signClass(p?.value) },

      { field: 'last', headerName: 'Price', minWidth: 130, sortable: true, renderCell: PriceDeltaCell },

      {
        field: 'wk_change',
        headerName: '1W',
        minWidth: 110,
        sortable: true,
        renderCell: makePeriodCell('wk_change', 'wk_change_pct'),
      },

      { field: 'ret_1m', headerName: '% 1M', width: 80, type: 'number', renderCell: renderPctCell, cellClassName: (p) => signClass(p?.value) },
      { field: 'ret_3m', headerName: '% 3M', width: 80, type: 'number', renderCell: renderPctCell, cellClassName: (p) => signClass(p?.value) },
      { field: 'ret_6m', headerName: '% 6M', width: 80, type: 'number', renderCell: renderPctCell, cellClassName: (p) => signClass(p?.value) },
      { field: 'ret_12_1m', headerName: '% 12–1M', width: 80, type: 'number', renderCell: renderPctCell, cellClassName: (p) => signClass(p?.value) },
      { field: 'pct_from_52w_high', headerName: '% 52W H', width: 90, type: 'number', renderCell: renderPctCell, cellClassName: (p) => signClass(p?.value) },
      

      { field: 'buy', headerName: 'Buy', width: 60 },

      {
        field: 'badges',
        headerName: 'Momentum',
        minWidth: 100,
        sortable: false,
        filterable: false,
        renderCell: BadgesCell,
      },

      {
        field: 'reason',
        headerName: 'Reason',
        flex: 1.2,
        minWidth: 10,
        sortable: false,
        renderCell: (p) => (
          <span
            style={{
              fontSize: 12,
              color: 'var(--mui-palette-text-secondary, #6b7280)',
              display: '-webkit-box',
              WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical',
              overflow: 'hidden',
              whiteSpace: 'normal',
              lineHeight: 1.25,
            }}
            title={String(p?.value ?? '')}
          >
            {String(p?.value ?? '')}
          </span>
        ),
      },

      //{ field: 'rsi', headerName: 'RSI', width: 80, type: 'number', renderCell: renderNum },
      //{ field: 'adx', headerName: 'ADX', width: 80, type: 'number', renderCell: renderNum },

      //{ field: 'atr_pct', headerName: 'ATR %', width: 80, type: 'number', renderCell: renderPctCell },
      { field: 'liquidity', headerName: 'Liquidity (M)', width: 110, type: 'number', renderCell: renderMillions },
      //{ field: 'vol_spike', headerName: 'xRel Vol', width: 80, type: 'number', renderCell: renderNum },
    ],
    [],
  );

  const boxSx = React.useMemo(() => ({
    width: '100%',
    minWidth: 0,           // let children shrink
    display: 'flex',
    flexDirection: 'column',
    minHeight: 0,          // important for flexbox overflow
    overflowX: 'hidden',   // avoid page-level horizontal scroll
  }), []);

  if (query.isError) {
    return (
      <Alert severity="error" sx={{ m: 1 }}>
        Failed to load screener
      </Alert>
    );
  }

  return (
    <Box className="datagrid-elevated" sx={boxSx}>
      <DataGrid
        autoHeight                
        sx={{ flex: 1, width: '100%', minWidth: 0 }}
        rows={rows}
        getRowId={getId}
        columns={columns}
        loading={query.isLoading || query.isFetching}
        slots={{ loadingOverlay: LinearLoadingOverlay }}
        paginationMode="server"
        rowCount={rowCount}
        paginationModel={pagination}
        onPaginationModelChange={(m) =>
          setPagination(prev => ({
            page: m.pageSize !== prev.pageSize ? 0 : m.page,           // reset page if pageSize changed
            pageSize: Math.min(MAX_PAGE_SIZE, Math.max(1, m.pageSize)), // clamp to MIT cap
          }))
        }
        pageSizeOptions={[10, 25, 50, 100]} // MIT cap
        sortingMode="server"
        sortModel={sortModel}
        onSortModelChange={setSortModel}
        disableColumnMenu
        density="compact"
        disableRowSelectionOnClick
        onRowClick={(p) => {
          const sym = p?.row?.symbol;
          if (sym) openDrawerFor(sym);
        }}
      />
      <RightDrawer symbol={drawerSymbol} open={drawerOpen} onClose={closeDrawer} />
    </Box>
  );
}
