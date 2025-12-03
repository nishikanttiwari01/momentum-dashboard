import * as React from 'react';
import {
  alpha,
  useTheme,
} from '@mui/material/styles';
import {
  Box,
  Chip,
  CircularProgress,
  Grid,
  Paper,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material';
import dayjs from 'dayjs';

import { useGetMomentumHeatmap } from '@/lib/api/client';
import type { MomentumHeatmapSector } from '@/lib/api/types';

const percentFormatter = new Intl.NumberFormat('en-US', {
  maximumFractionDigits: 2,
  signDisplay: 'exceptZero',
});

const ratioFormatter = new Intl.NumberFormat('en-US', {
  maximumFractionDigits: 2,
});

const momentFormatter = new Intl.NumberFormat('en-US', {
  maximumFractionDigits: 2,
  signDisplay: 'exceptZero',
});

const turnoverLabel = (value?: number | null) =>
  value == null ? '—' : `${ratioFormatter.format(value)}×`;
const percentLabel = (value?: number | null) =>
  value == null ? '—' : `${percentFormatter.format(value)}%`;

const FALLBACK_SECTORS: MomentumHeatmapSector[] = [
  { name: 'BANK', symbol: 'NIFTYBANK', change_1d: 0.8, change_1w: 1.9, change_1m: 3.4, turnover_ratio: 1.6, momentum_score: 0.62 },
  { name: 'FIN SERVICES', symbol: 'NIFTYFIN', change_1d: 0.5, change_1w: 1.2, change_1m: 2.8, turnover_ratio: 1.3, momentum_score: 0.55 },
  { name: 'IT', symbol: 'NIFTYIT', change_1d: -0.2, change_1w: 0.6, change_1m: 1.1, turnover_ratio: 0.9, momentum_score: 0.48 },
  { name: 'PHARMA', symbol: 'NIFTYPHARMA', change_1d: 0.3, change_1w: 1.4, change_1m: 2.1, turnover_ratio: 0.8, momentum_score: 0.52 },
  { name: 'AUTO', symbol: 'NIFTYAUTO', change_1d: 0.9, change_1w: 2.2, change_1m: 4.1, turnover_ratio: 1.1, momentum_score: 0.66 },
  { name: 'FMCG', symbol: 'NIFTYFMCG', change_1d: 0.1, change_1w: 0.5, change_1m: 1.0, turnover_ratio: 0.7, momentum_score: 0.44 },
  { name: 'METAL', symbol: 'NIFTYMETAL', change_1d: -0.6, change_1w: -1.4, change_1m: 0.3, turnover_ratio: 1.0, momentum_score: 0.38 },
  { name: 'REALTY', symbol: 'NIFTYREALTY', change_1d: 1.2, change_1w: 2.9, change_1m: 5.5, turnover_ratio: 0.9, momentum_score: 0.72 },
];

const useTileColors = (delta: number) => {
  const theme = useTheme();
  const abs = Math.abs(delta);
  const intensity = Math.min(abs / 6, 1);
  const base = delta >= 0 ? theme.palette.success.main : theme.palette.error.main;
  return {
    chipColor: delta >= 0 ? 'success' : 'error',
    borderColor: alpha(base, 0.6),
    background: alpha(base, 0.12 + intensity * 0.25),
  };
};

type HeatmapCardProps = {
  sector: MomentumHeatmapSector;
};

const HeatmapCard: React.FC<HeatmapCardProps> = ({ sector }) => {
  const colors = useTileColors(sector.change_1d ?? 0);

  return (
    <Box
      sx={{
        p: 1.5,
        height: '100%',
        borderRadius: 2,
        bgcolor: colors.background,
        border: '1px solid',
        borderColor: colors.borderColor,
        display: 'flex',
        flexDirection: 'column',
        gap: 1.5,
      }}
    >
      <Stack direction="row" alignItems="center" justifyContent="space-between" spacing={1}>
        <Box>
          <Typography variant="subtitle2" sx={{ lineHeight: 1.1 }}>
            {sector.name}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {sector.symbol}
          </Typography>
        </Box>
        <Chip
          size="small"
          color={colors.chipColor as any}
          label={percentLabel(sector.change_1d)}
          sx={{ fontWeight: 600 }}
        />
      </Stack>

      <Grid container spacing={1}>
        <Grid item xs={6}>
          <Metric label="1 Week" value={percentLabel(sector.change_1w)} tone={sector.change_1w ?? 0} />
        </Grid>
        <Grid item xs={6}>
          <Metric label="1 Month" value={percentLabel(sector.change_1m)} tone={sector.change_1m ?? 0} />
        </Grid>
        <Grid item xs={6}>
          <Metric label="Turnover" value={turnoverLabel(sector.turnover_ratio)} />
        </Grid>
        <Grid item xs={6}>
          <Metric
            label="Momentum"
            value={
              sector.momentum_score != null ? momentFormatter.format(sector.momentum_score * 100) + '%' : '—'
            }
            tone={sector.momentum_score ?? 0}
          />
        </Grid>
      </Grid>

      {sector.advance_decline ? (
        <Typography variant="caption" color="text.secondary">
          Adv {sector.advance_decline.advancers} • Dec {sector.advance_decline.decliners}
          {sector.advance_decline.unchanged != null
            ? ` • Unch ${sector.advance_decline.unchanged}`
            : null}
        </Typography>
      ) : null}

      {sector.note ? (
        <Tooltip title={sector.note}>
          <Typography variant="caption" color="warning.main" noWrap>
            {sector.note}
          </Typography>
        </Tooltip>
      ) : null}
    </Box>
  );
};

type MetricProps = {
  label: string;
  value: string;
  tone?: number;
};

const Metric: React.FC<MetricProps> = ({ label, value, tone }) => {
  const theme = useTheme();
  let color: string | undefined;
  if (tone != null) {
    color =
      tone > 0
        ? theme.palette.success.dark
        : tone < 0
        ? theme.palette.error.dark
        : theme.palette.text.secondary;
  }
  return (
    <Box>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="body2" fontWeight={600} color={color}>
        {value}
      </Typography>
    </Box>
  );
};

type SectorHeatmapProps = {
  refetchIntervalMs?: number | false;
};

const REFRESH_DEFAULT = 5 * 60 * 1000;

const SectorHeatmap: React.FC<SectorHeatmapProps> = ({ refetchIntervalMs }) => {
  const heatmapQuery = useGetMomentumHeatmap(
    { include_constituents: false, include_industries: false },
    {
      axios: { baseURL: '' },
      query: {
        staleTime: 60_000,
        refetchInterval: refetchIntervalMs ?? REFRESH_DEFAULT,
        refetchOnWindowFocus: false,
        refetchOnReconnect: false,
        retry: 1,
      },
    }
  );

  const payload = heatmapQuery.data?.data;
  const usingFallback = !payload?.sectors || payload.sectors.length === 0;
  const sectors = usingFallback ? FALLBACK_SECTORS : payload!.sectors;
  const statusNote = usingFallback
    ? 'Live feed unavailable; showing fallback sectors.'
    : heatmapQuery.isError && heatmapQuery.error instanceof Error
    ? heatmapQuery.error.message
    : heatmapQuery.isError
    ? 'Unable to load momentum heatmap right now.'
    : null;

  return (
    <Paper sx={{ p: 2, width: '100%' }}>
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        alignItems={{ xs: 'flex-start', sm: 'center' }}
        justifyContent="space-between"
        sx={{ mb: statusNote ? 1 : 1, flexWrap: 'wrap', gap: 1 }}
      >
        <Stack direction="row" alignItems="center" spacing={1} flexWrap="wrap">
          <Typography variant="subtitle1" sx={{ fontWeight: 800, letterSpacing: '.02em' }}>
            Sector Momentum Heatmap
          </Typography>
          {statusNote ? (
            <Typography variant="caption" color="warning.main">
              {statusNote}
            </Typography>
          ) : null}
        </Stack>

        {payload ? (
          <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap">
            <Typography variant="caption" color="text.secondary">
              {`Session ${payload.session.toUpperCase()} — ${dayjs(payload.as_of).format('DD MMM, HH:mm')} IST`}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              NSE trade date {dayjs(payload.trade_date).format('DD MMM YYYY')}
            </Typography>
          </Stack>
        ) : null}
      </Stack>

      {heatmapQuery.isLoading && !payload ? (
        <Stack alignItems="center" justifyContent="center" sx={{ py: 4 }}>
          <CircularProgress size={24} />
        </Stack>
      ) : sectors && sectors.length ? (
        <Grid
          container
          spacing={1.5}
          columns={{ xs: 12, sm: 12, md: 18, lg: 24 }}
        >
          {sectors.map((sector) => (
            <Grid item key={sector.symbol} xs={12} sm={6} md={4} lg={3}>
              <HeatmapCard sector={sector} />
            </Grid>
          ))}
        </Grid>
      ) : (
        <Typography variant="body2" color="text.secondary">
          No sectors available.
        </Typography>
      )}

      {payload?.notes?.length ? (
        <Box sx={{ mt: 2 }}>
          {payload.notes.map((note) => (
            <Typography key={note} variant="caption" color="text.secondary" display="block">
              • {note}
            </Typography>
          ))}
        </Box>
      ) : null}
    </Paper>
  );
};

export default SectorHeatmap;
