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
  Link as MuiLink,
} from '@mui/material';
import { Link } from 'react-router-dom';
import axios from 'axios';
import { useQuery } from '@tanstack/react-query';

type Accum = {
  status: string;
  drawdown_from_1y_high_pct: number | null;
  reasons: string[];
};

type Perf = {
  latest_nav?: number | null;
  ret_1m_pct?: number | null;
  ret_6m_pct?: number | null;
  ret_1y_pct?: number | null;
  drawdown_from_1y_high_pct?: number | null;
};

type Inst = {
  id: string;
  name: string;
  category: string;
  type: string;
  performance: Perf | null;
  accumulation: Accum | null;
};

type Overview = { configured: boolean; instruments: Inst[] };

const STATUS_META: Record<string, { label: string; color: 'info' | 'warning' }> = {
  watch: { label: 'Watch', color: 'info' },
  tranche_eligible: { label: 'Tranche', color: 'warning' },
};

const num = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 });

const PctCell: React.FC<{ v: number | null | undefined }> = ({ v }) => (
  <TableCell
    align="right"
    sx={{
      py: 0.5,
      fontVariantNumeric: 'tabular-nums',
      color: v == null ? 'text.disabled' : v >= 0 ? '#00B386' : '#F04438',
      fontWeight: 600,
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

const AccumulationWatchCard: React.FC = () => {
  const query = useQuery({
    queryKey: ['portfolio-overview'],
    queryFn: async () => (await axios.get<Overview>('/api/v1/portfolio/overview')).data,
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });

  const data = query.data;
  if (query.isError || (data && !data.configured)) return null;

  const signals = (data?.instruments ?? []).filter(
    (i) => i.accumulation && i.accumulation.status !== 'no_action'
  );

  return (
    <Paper sx={{ p: 2 }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 800, letterSpacing: '.02em' }}>
          MF Accumulation Watch
        </Typography>
        <MuiLink component={Link} to="/portfolio" variant="caption">
          Open portfolio →
        </MuiLink>
      </Stack>

      {query.isLoading ? (
        <Typography variant="caption" color="text.secondary">
          Loading fund NAVs…
        </Typography>
      ) : signals.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          No funds in the configured dip zone right now.
        </Typography>
      ) : (
        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small" sx={{ '& td, & th': { borderBottom: '1px solid #F2F2F2' } }}>
            <TableHead>
              <TableRow>
                <TableCell sx={headSx}>Fund</TableCell>
                <TableCell sx={headSx} align="right">NAV</TableCell>
                <TableCell sx={headSx} align="right">1M</TableCell>
                <TableCell sx={headSx} align="right">6M</TableCell>
                <TableCell sx={headSx} align="right">1Y</TableCell>
                <TableCell sx={headSx} align="right">▼ 1Y High</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {signals.map((s) => {
                const perf = s.performance ?? {};
                const dd = s.accumulation!.drawdown_from_1y_high_pct ?? perf.drawdown_from_1y_high_pct;
                const meta = STATUS_META[s.accumulation!.status];
                return (
                  <TableRow key={s.id} hover>
                    <TableCell sx={{ py: 0.5 }}>
                      <Tooltip title={s.accumulation!.reasons.join(' • ')} arrow>
                        <Stack direction="row" spacing={0.75} alignItems="center">
                          <Chip
                            size="small"
                            color={meta?.color ?? 'info'}
                            label={meta?.label ?? s.accumulation!.status}
                            sx={{ height: 20, fontSize: 11 }}
                          />
                          <Typography variant="body2" fontWeight={600} noWrap sx={{ maxWidth: 220 }}>
                            {s.name.replace(/ - Direct Growth$/i, '')}
                          </Typography>
                        </Stack>
                      </Tooltip>
                    </TableCell>
                    <TableCell align="right" sx={{ py: 0.5, fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}>
                      {perf.latest_nav != null ? `₹${num.format(perf.latest_nav)}` : '—'}
                    </TableCell>
                    <PctCell v={perf.ret_1m_pct} />
                    <PctCell v={perf.ret_6m_pct} />
                    <PctCell v={perf.ret_1y_pct} />
                    <TableCell
                      align="right"
                      sx={{
                        py: 0.5,
                        fontVariantNumeric: 'tabular-nums',
                        fontWeight: 700,
                        whiteSpace: 'nowrap',
                        color:
                          dd == null
                            ? 'text.disabled'
                            : Math.abs(Math.min(dd, 0)) >= 10
                              ? '#F04438'
                              : '#B54708',
                      }}
                    >
                      {dd == null ? '—' : `${num.format(dd)}%`}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </Box>
      )}
    </Paper>
  );
};

export default AccumulationWatchCard;
