// src/components/MomentumTable.tsx
import * as React from 'react';
import {
  DataGrid,
  GridColDef,
  GridPaginationModel,
  GridRenderCellParams,
  GridSortModel,
} from '@mui/x-data-grid';
import { Box, Alert, LinearProgress, Tooltip, Chip, alpha } from '@mui/material';
import { useGetApiV1Screener } from '@/lib/api/client';
import type { GetApiV1ScreenerParams } from '@/lib/api/types';
import RightDrawer from '@/features/detail/RightDrawer';

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
  const pctAsRatio =
    pctRaw == null ? null : Math.abs(pctRaw) <= 1 ? pctRaw : pctRaw / 100;
  const absChange =
    last != null && pctAsRatio != null ? last * pctAsRatio : null;

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

// only keep supported categories, normalize to UPPER
const normalizeBadges = (row: any): Badge[] => {
  const raw = Array.isArray(row?.badges) ? row.badges : [];
  const allowed = new Set(['BREAKOUT','MOMENTUM','WATCH','IGNORE']);
  return raw
    .map((b: any) => ({
      label: String(b?.label ?? '').trim(),
      category: String(b?.category ?? '').toUpperCase() as Badge['category'],
    }))
    .filter((b: Badge) => b.label && allowed.has(b.category));
};

// nice colors (purple & vermilion theme) + subtle backgrounds
const chipSx = (cat: Badge['category']) => (theme: any) => {
  const base = {
    fontWeight: 700,
    height: 22,
    borderWidth: 1,
    '& .MuiChip-label': { px: 1, whiteSpace: 'nowrap' },
  } as const;

  switch (cat) {
    case 'MOMENTUM': {
      const c = '#7C4DFF'; // purple
      return { ...base, color: c, borderColor: alpha(c, .35), bgcolor: alpha(c, .10) };
    }
    case 'BREAKOUT': {
      const c = theme.palette.success.main;
      return { ...base, color: c, borderColor: alpha(c, .35), bgcolor: alpha(c, .10) };
    }
    case 'WATCH': {
      const c = theme.palette.info.main;
      return { ...base, color: c, borderColor: alpha(c, .35), bgcolor: alpha(c, .10) };
    }
    case 'IGNORE': {
      const c = theme.palette.text.secondary;
      return { ...base, color: c, borderColor: alpha(c, .25), bgcolor: alpha(c, .08) };
    }
    default:
      return base;
  }
};

// optional priority: show most actionable first
const BADGE_ORDER: Badge['category'][] = ['ACTION','BREAKOUT','MOMENTUM','WATCH','IGNORE'];

const BadgesCell = (params: any) => {
  const badges = normalizeBadges(params?.row)
    .sort((a, b) => BADGE_ORDER.indexOf(a.category) - BADGE_ORDER.indexOf(b.category));

  const max = 2; // show up to 2; rest go in a "+N" chip
  const shown = badges.slice(0, max);
  const extra = badges.length - shown.length;

  return (
    <Box sx={{ display: 'flex', gap: 0.5, overflow: 'hidden' }}>
      {shown.map((b, i) => (
        <Chip key={`${b.category}-${i}`} size="small" label={b.label} variant="outlined" sx={chipSx(b.category)} />
      ))}
      {extra > 0 && (
        <Tooltip title={badges.slice(max).map(b => b.label).join(', ')}>
          <Chip size="small" label={`+${extra}`} variant="outlined" sx={{ height: 22, fontWeight: 700 }} />
        </Tooltip>
      )}
    </Box>
  );
};

// ---------- combined 1W: Price + Δ + % ----------
// ---------- Common period cell: shows PRIOR price + "±Δ (±%)" ----------
const makePeriodCell =
  (absKey?: string, pctKey?: string) =>
  (params: GridRenderCellParams) => {
    const last = normalizeNumber(params?.row?.last);

    const absRaw = absKey ? normalizeNumber(params?.row?.[absKey as any]) : null;
    const pctRaw = pctKey ? normalizeNumber(params?.row?.[pctKey as any]) : null;

    // percent may come as 0.12 or 12 → normalize to decimal
    const pctDec =
      pctRaw == null ? null : Math.abs(pctRaw) <= 1 ? pctRaw : pctRaw / 100;

    // compute prior price (price at start of period)
    let prior: number | null = null;
    let deltaAbs: number | null = null;

    if (last != null) {
      if (absRaw != null) {
        deltaAbs = absRaw;
        prior = last - deltaAbs;
      } else if (pctDec != null && isFinite(pctDec) && pctDec > -0.9999) {
        // prior * (1 + pct) = last  => prior = last / (1 + pct)
        prior = last / (1 + pctDec);
        deltaAbs = last - prior; // exact absolute change derived from pct
      }
    }

    const pos = (pctRaw ?? deltaAbs ?? 0) >= 0;
    const sign = pos ? '+' : '';
    const colorClass = pos ? 'text-pos' : 'text-neg';

    const priorStr = prior == null ? '—'
      : new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(prior);
    const absStr = deltaAbs == null ? ''
      : new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(deltaAbs);
    const pctStr = pctRaw == null ? '' : fmtPct(pctRaw);

    return (
      <Box sx={{ display: 'flex', flexDirection: 'column', lineHeight: 1.2, py: 0.5 }}>
        <span>{priorStr}</span>
        {(absStr || pctStr) && (
          <span className={colorClass} style={{ fontSize: 12 }}>
            {sign}{absStr}{absStr ? ' ' : ''}{pctStr ? `(${pctStr})` : ''}
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


export default function MomentumTable({ refetchIntervalMs = false }: { refetchIntervalMs?: number | false }) {
  const [pagination, setPagination] = React.useState<GridPaginationModel>({ page: 0, pageSize: 25 });
  const [sortModel, setSortModel] = React.useState<GridSortModel>([]);

  // Drawer
  const [drawerOpen, setDrawerOpen] = React.useState(false);
  const [drawerSymbol, setDrawerSymbol] = React.useState<string | null>(null);
  const openDrawerFor = (symbol: string) => { setDrawerSymbol(symbol); setDrawerOpen(true); };
  const closeDrawer = () => { setDrawerOpen(false); setDrawerSymbol(null); };

  // --- query + server-side pagination/sort params
  const apiParams: GetApiV1ScreenerParams = {
    page: pagination.page + 1,
    page_size: pagination.pageSize,
  };
  const s0 = sortModel[0];
  if (s0?.field) {
    (apiParams as any).sort_by = s0.field;
    (apiParams as any).sort_dir = s0.sort ?? 'asc';
  }

  const query = useGetApiV1Screener(apiParams, {
    axios: { baseURL: '' },
    query: {
      keepPreviousData: true,
      refetchInterval: refetchIntervalMs || false,
      retry: 0,
    },
  });

  // ✅ rows defined here (do not remove)
  const payload = query.data?.data as any;
  const rows: any[] = payload?.items ?? payload?.rows ?? [];
  const rowCount: number = payload?.total ?? rows.length;
  const getId = (r: any) => r.id ?? r.symbol ?? `${r.ticker ?? ''}-${r.symbol ?? ''}`;

  // cell renderers to avoid blanks
  const renderNum = (p: any) => <span>{fmtNum(p?.value)}</span>;
  const renderPct = (p: any) => <span className={signClass(p?.value)}>{fmtPct(p?.value)}</span>;

  const columns = React.useMemo<GridColDef[]>(
    () => [
      { field: 'symbol', headerName: 'Ticker', minWidth: 150 },

      { field: 'score', headerName: 'Score', width: 70, type: 'number', renderCell: renderNum, cellClassName: (p) => signClass(p?.value) },

      // Combined Price + %Today
      { field: 'last', headerName: 'Price', minWidth: 130, sortable: true, renderCell: PriceDeltaCell },

      // Weekly change
      //{ field: 'wk_change', headerName: 'Δ 1W', width: 60, type: 'number', renderCell: renderNum, cellClassName: (p) => signClass(p?.value) },
      //{ field: 'wk_change_pct', headerName: '% 1W', width: 90, type: 'number', renderCell: renderPct, cellClassName: (p) => signClass(p?.value) },
      {
        field: 'wk_change',               // keep field for sorting
        headerName: '1W',
        minWidth: 110,
        sortable: true,
        renderCell: makePeriodCell('wk_change', 'wk_change_pct'),
      },
      // Momentum windows
      { field: 'ret_1m', headerName: '% 1M', width: 80, type: 'number', renderCell: renderPct, cellClassName: (p) => signClass(p?.value) },
      { field: 'ret_3m', headerName: '% 3M', width: 80, type: 'number', renderCell: renderPct, cellClassName: (p) => signClass(p?.value) },
      { field: 'ret_6m', headerName: '% 6M', width: 80, type: 'number', renderCell: renderPct, cellClassName: (p) => signClass(p?.value) },
      { field: 'ret_12_1m', headerName: '% 12–1M', width: 80, type: 'number', renderCell: renderPct, cellClassName: (p) => signClass(p?.value) },

      {
        field: 'pct_from_52w_high',
        headerName: '52W H',
        width: 80,
        type: 'number',
        renderCell: (p) => {
          const n = normalizeNumber(p?.value);
          const cls = n == null ? '' : n > 0 ? 'text-neg' : n < 0 ? 'text-pos' : '';
          return <span className={cls}>{fmtPct(p?.value)}</span>;
        },
      },
      { field: 'buy', headerName: 'Buy', width: 70 },
      // old:
// { field: 'reason', headerName: 'Reason', flex: 1.2, minWidth: 210 },
{
  field: 'badges',
  headerName: 'Momentum',
  minWidth: 180,
  sortable: false,
  filterable: false,
  renderCell: BadgesCell,
},

// new (2-line small text with ellipsis)
      {
        field: 'reason',
        headerName: 'Reason',
        flex: 1.2,
        minWidth: 200,
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
            title={String(p?.value ?? '')} // full text on hover
          >
            {String(p?.value ?? '')}
          </span>
        ),
      },

      // Indicators
      { field: 'rsi', headerName: 'RSI', width: 80, type: 'number', renderCell: renderNum },
      { field: 'adx', headerName: 'ADX', width: 80, type: 'number', renderCell: renderNum },

      // Others

      { field: 'atr_pct', headerName: 'ATR %', width: 80, type: 'number', renderCell: renderPct },
      { field: 'liquidity', headerName: 'Liquidity (M)', width: 110, type: 'number', renderCell: renderMillions },

      { field: 'vol_spike', headerName: 'xRel Vol', width: 80, type: 'number', renderCell: renderNum },

      
    ],
    []
  );

  if (query.isError) {
    return <Alert severity="error" sx={{ m: 1 }}>Failed to load screener</Alert>;
  }
  // ---------- combined 1W Δ + %1W cell ----------

  return (
    <Box className="datagrid-elevated" sx={{ height: 720, width: '100%' }}>
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
        pageSizeOptions={[10, 25, 50, 100,500]}
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
