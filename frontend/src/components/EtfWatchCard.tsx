import * as React from 'react';
import {
  Box,
  Chip,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from '@mui/material';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import TrendingDownIcon from '@mui/icons-material/TrendingDown';
import TrendingFlatIcon from '@mui/icons-material/TrendingFlat';
import axios from 'axios';
import { useQuery } from '@tanstack/react-query';

type EtfRow = {
  symbol: string;
  name: string;
  category: string;
  last_price: number | null;
  ret_1m_pct: number | null;
  ret_3m_pct: number | null;
  ret_6m_pct: number | null;
  ret_1y_pct: number | null;
  pct_from_52w_high: number | null;
  trend: 'up' | 'down' | 'mixed' | 'unknown';
  error: string | null;
};

type Snapshot = {
  configured: boolean;
  generated_at?: string;
  rank_by?: string;
  top_n?: number;
  stale?: boolean;
  etfs: EtfRow[];
};

const CATEGORY_LABEL: Record<string, string> = {
  EQUITY_INDEX: 'Index',
  EQUITY_SECTOR: 'Sector',
  EQUITY_FACTOR: 'Factor',
  INTERNATIONAL: 'Intl',
  COMMODITY: 'Commodity',
};

const num = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 });

const PctCell: React.FC<{ v: number | null | undefined; bold?: boolean }> = ({ v, bold }) => (
  <TableCell
    align="right"
    sx={{
      py: 0.5,
      fontVariantNumeric: 'tabular-nums',
      color: v == null ? 'text.disabled' : v >= 0 ? '#00B386' : '#F04438',
      fontWeight: bold ? 700 : 600,
      whiteSpace: 'nowrap',
    }}
  >
    {v == null ? '—' : `${v > 0 ? '+' : ''}${num.format(v)}%`}
  </TableCell>
);

const headSx = {
  py: 0.5,
  fontSize: 11,
  color: 'text.secondary',
  textTransform: 'uppercase' as const,
  letterSpacing: '0.05em',
  whiteSpace: 'nowrap' as const,
};

const TrendChip: React.FC<{ trend: EtfRow['trend'] }> = ({ trend }) => {
  if (trend === 'up')
    return <Chip size="small" icon={<TrendingUpIcon />} label="Uptrend" sx={{ height: 20, fontSize: 11, bgcolor: '#E6F7F1', color: '#00795B', '& .MuiChip-icon': { color: '#00B386', fontSize: 14 } }} />;
  if (trend === 'down')
    return <Chip size="small" icon={<TrendingDownIcon />} label="Downtrend" sx={{ height: 20, fontSize: 11, bgcolor: '#FEECEB', color: '#B42318', '& .MuiChip-icon': { color: '#F04438', fontSize: 14 } }} />;
  if (trend === 'mixed')
    return <Chip size="small" icon={<TrendingFlatIcon />} label="Mixed" sx={{ height: 20, fontSize: 11, bgcolor: '#F4F4F5', color: '#6b6b6b', '& .MuiChip-icon': { fontSize: 14 } }} />;
  return <Chip size="small" label="—" sx={{ height: 20, fontSize: 11 }} />;
};

const EtfWatchCard: React.FC = () => {
  const query = useQuery({
    queryKey: ['etf-trending'],
    queryFn: async () => (await axios.get<Snapshot>('/api/v1/etfs/trending')).data,
    staleTime: 30 * 60 * 1000,
    retry: 1,
  });

  const data = query.data;
  if (query.isError || (data && !data.configured)) return null;

  const rows = (data?.etfs ?? []).filter((e) => !e.error).slice(0, data?.top_n ?? 8);

  return (
    <Paper sx={{ p: 2 }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1, flexWrap: 'wrap', gap: 1 }}>
        <Stack direction="row" spacing={1} alignItems="center">
          <Typography variant="subtitle1" sx={{ fontWeight: 800, letterSpacing: '.02em' }}>
            ETF Momentum Watch
          </Typography>
          {data?.stale ? (
            <Chip size="small" label="cached" sx={{ height: 20, fontSize: 11 }} />
          ) : null}
        </Stack>
        <Typography variant="caption" color="text.secondary">
          Curated NSE ETFs · ranked by 3M return
        </Typography>
      </Stack>

      {query.isLoading ? (
        <Typography variant="caption" color="text.secondary">
          Loading ETF prices…
        </Typography>
      ) : rows.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          ETF price data unavailable right now.
        </Typography>
      ) : (
        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small" sx={{ '& td, & th': { borderBottom: '1px solid #F2F2F2' } }}>
            <TableHead>
              <TableRow>
                <TableCell sx={headSx}>ETF</TableCell>
                <TableCell sx={headSx} align="right">Price</TableCell>
                <TableCell sx={headSx} align="right">1M</TableCell>
                <TableCell sx={headSx} align="right">3M</TableCell>
                <TableCell sx={headSx} align="right">6M</TableCell>
                <TableCell sx={headSx} align="right">1Y</TableCell>
                <TableCell sx={headSx} align="right">▼ 52W High</TableCell>
                <TableCell sx={headSx}>Trend</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((e) => (
                <TableRow key={e.symbol} hover>
                  <TableCell sx={{ py: 0.5 }}>
                    <Tooltip title={e.name} arrow>
                      <Stack direction="row" spacing={0.75} alignItems="center">
                        <Typography variant="body2" fontWeight={700} sx={{ fontFamily: 'monospace' }}>
                          {e.symbol}
                        </Typography>
                        <Chip
                          size="small"
                          label={CATEGORY_LABEL[e.category] ?? e.category}
                          sx={{ height: 18, fontSize: 10, bgcolor: '#F4F4F5', color: '#6b6b6b' }}
                        />
                      </Stack>
                    </Tooltip>
                  </TableCell>
                  <TableCell align="right" sx={{ py: 0.5, fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}>
                    {e.last_price != null ? `₹${num.format(e.last_price)}` : '—'}
                  </TableCell>
                  <PctCell v={e.ret_1m_pct} />
                  <PctCell v={e.ret_3m_pct} bold />
                  <PctCell v={e.ret_6m_pct} />
                  <PctCell v={e.ret_1y_pct} />
                  <TableCell
                    align="right"
                    sx={{ py: 0.5, fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap', color: 'text.secondary' }}
                  >
                    {e.pct_from_52w_high == null ? '—' : `${num.format(e.pct_from_52w_high)}%`}
                  </TableCell>
                  <TableCell sx={{ py: 0.5 }}>
                    <TrendChip trend={e.trend} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Box>
      )}
    </Paper>
  );
};

export default EtfWatchCard;
