import * as React from 'react';
import {
  Box,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';
import axios from 'axios';
import { useQuery } from '@tanstack/react-query';

type Period = '3m' | '6m' | '1y';

type PerformerRow = {
  symbol: string;
  name: string | null;
  sector: string | null;
  price: number | null;
  ret_pct: number;
  score: number | null;
  pct_from_52w_high: number | null;
};

type Payload = {
  period: Period;
  as_of: string | null;
  items: PerformerRow[];
};

const PERIOD_LABEL: Record<Period, string> = { '3m': '3M', '6m': '6M', '1y': '1Y' };

const num = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 });

const headSx = {
  py: 0.5,
  fontSize: 11,
  color: 'text.secondary',
  textTransform: 'uppercase' as const,
  letterSpacing: '0.05em',
  whiteSpace: 'nowrap' as const,
};

type Props = {
  onOpenSymbol?: (symbol: string) => void;
};

const TopPerformersCard: React.FC<Props> = ({ onOpenSymbol }) => {
  const [period, setPeriod] = React.useState<Period>('6m');

  const query = useQuery({
    queryKey: ['top-performers', period],
    queryFn: async () =>
      (await axios.get<Payload>('/api/v1/screener/top-performers', { params: { period, limit: 10 } })).data,
    staleTime: 10 * 60 * 1000,
    retry: 1,
  });

  const items = query.data?.items ?? [];

  return (
    <Paper sx={{ p: 2 }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1, flexWrap: 'wrap', gap: 1 }}>
        <Stack direction="row" spacing={1} alignItems="baseline">
          <Typography variant="subtitle1" sx={{ fontWeight: 800, letterSpacing: '.02em' }}>
            Top Performers
          </Typography>
          <Typography variant="caption" color="text.secondary">
            best {PERIOD_LABEL[period]} returns · any size{period === '1y' ? ' · 12M ex last month' : ''}
          </Typography>
        </Stack>
        <ToggleButtonGroup size="small" exclusive value={period} onChange={(_, v) => v && setPeriod(v)}>
          {(['3m', '6m', '1y'] as Period[]).map((p) => (
            <ToggleButton key={p} value={p} sx={{ px: 1.25, py: 0.25 }}>
              {PERIOD_LABEL[p]}
            </ToggleButton>
          ))}
        </ToggleButtonGroup>
      </Stack>

      {query.isLoading ? (
        <Typography variant="caption" color="text.secondary">
          Loading returns…
        </Typography>
      ) : query.isError ? (
        <Typography variant="body2" color="text.secondary">
          Could not load top performers.
        </Typography>
      ) : items.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          No return data in the latest scan snapshot.
        </Typography>
      ) : (
        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small" sx={{ '& td, & th': { borderBottom: '1px solid #F2F2F2' } }}>
            <TableHead>
              <TableRow>
                <TableCell sx={headSx}>#</TableCell>
                <TableCell sx={headSx}>Stock</TableCell>
                <TableCell sx={headSx}>Sector</TableCell>
                <TableCell sx={headSx} align="right">Price</TableCell>
                <TableCell sx={headSx} align="right">{PERIOD_LABEL[period]} Return</TableCell>
                <TableCell sx={headSx} align="right">Score</TableCell>
                <TableCell sx={headSx} align="right">▼ 52W High</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {items.map((r, i) => (
                <TableRow
                  key={r.symbol}
                  hover
                  onClick={onOpenSymbol ? () => onOpenSymbol(r.symbol) : undefined}
                  sx={onOpenSymbol ? { cursor: 'pointer' } : undefined}
                >
                  <TableCell sx={{ py: 0.5, color: 'text.secondary' }}>{i + 1}</TableCell>
                  <TableCell sx={{ py: 0.5 }}>
                    <Stack>
                      <Typography variant="body2" fontWeight={700} sx={{ fontFamily: 'monospace' }}>
                        {r.symbol.replace(/\.NS$/i, '')}
                      </Typography>
                      {r.name ? (
                        <Typography variant="caption" color="text.secondary" noWrap sx={{ maxWidth: 200 }}>
                          {r.name}
                        </Typography>
                      ) : null}
                    </Stack>
                  </TableCell>
                  <TableCell sx={{ py: 0.5, whiteSpace: 'nowrap', color: 'text.secondary', fontSize: 12 }}>
                    {r.sector ?? '—'}
                  </TableCell>
                  <TableCell align="right" sx={{ py: 0.5, fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}>
                    {r.price != null ? `₹${num.format(r.price)}` : '—'}
                  </TableCell>
                  <TableCell
                    align="right"
                    sx={{
                      py: 0.5,
                      fontVariantNumeric: 'tabular-nums',
                      fontWeight: 700,
                      whiteSpace: 'nowrap',
                      color: r.ret_pct >= 0 ? '#00B386' : '#F04438',
                    }}
                  >
                    {`${r.ret_pct > 0 ? '+' : ''}${num.format(r.ret_pct)}%`}
                  </TableCell>
                  <TableCell align="right" sx={{ py: 0.5, fontVariantNumeric: 'tabular-nums' }}>
                    {r.score != null ? num.format(r.score) : '—'}
                  </TableCell>
                  <TableCell align="right" sx={{ py: 0.5, fontVariantNumeric: 'tabular-nums', color: 'text.secondary', whiteSpace: 'nowrap' }}>
                    {r.pct_from_52w_high == null ? '—' : `${num.format(r.pct_from_52w_high)}%`}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Box>
      )}
      {query.data?.as_of ? (
        <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
          From scan snapshot as of {query.data.as_of}
        </Typography>
      ) : null}
    </Paper>
  );
};

export default TopPerformersCard;
