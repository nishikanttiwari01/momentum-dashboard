import * as React from 'react';
import {
  Box,
  CircularProgress,
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

// Flat bright cells (approved design): strong fill for big moves, tint for small.
const tileStyle = (delta: number) => {
  const abs = Math.abs(delta);
  if (delta >= 0) {
    if (abs >= 3) return { bg: '#00B386', fg: '#fff', sub: 'rgba(255,255,255,0.85)' };
    if (abs >= 1.5) return { bg: '#3ECFA4', fg: '#fff', sub: 'rgba(255,255,255,0.85)' };
    if (abs >= 0.5) return { bg: '#A7ECD8', fg: '#065F46', sub: '#0B7A5C' };
    return { bg: '#E9F9F3', fg: '#065F46', sub: '#5B9E8C' };
  }
  if (abs >= 3) return { bg: '#F04438', fg: '#fff', sub: 'rgba(255,255,255,0.85)' };
  if (abs >= 1.5) return { bg: '#FF7A70', fg: '#fff', sub: 'rgba(255,255,255,0.85)' };
  if (abs >= 0.5) return { bg: '#FCA5A5', fg: '#7F1D1D', sub: '#9C3333' };
  return { bg: '#FDEEEC', fg: '#7F1D1D', sub: '#B36B6B' };
};

type HeatmapCardProps = {
  sector: MomentumHeatmapSector;
};

const HeatmapCard: React.FC<HeatmapCardProps> = ({ sector }) => {
  const s = tileStyle(sector.change_1d ?? 0);
  const tip = (
    <Box sx={{ fontSize: 12, lineHeight: 1.7 }}>
      <b>{sector.name}</b> ({sector.symbol})<br />
      1W {percentLabel(sector.change_1w)} · 1M {percentLabel(sector.change_1m)}<br />
      Turnover {turnoverLabel(sector.turnover_ratio)} · Momentum{' '}
      {sector.momentum_score != null ? momentFormatter.format(sector.momentum_score * 100) + '%' : '—'}
      {sector.advance_decline ? (
        <>
          <br />
          Adv {sector.advance_decline.advancers} · Dec {sector.advance_decline.decliners}
        </>
      ) : null}
      {sector.note ? (
        <>
          <br />
          {sector.note}
        </>
      ) : null}
    </Box>
  );

  return (
    <Tooltip title={tip} arrow>
      <Box
        sx={{
          p: 1.1,
          borderRadius: '6px',
          bgcolor: s.bg,
          cursor: 'default',
          minHeight: 64,
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
        }}
      >
        <Stack direction="row" justifyContent="space-between" alignItems="baseline">
          <Typography sx={{ fontSize: 11.5, fontWeight: 700, color: s.fg, letterSpacing: '.02em' }} noWrap>
            {sector.name.replace('NIFTY ', '')}
          </Typography>
          <Typography sx={{ fontSize: 13, fontWeight: 700, color: s.fg, fontVariantNumeric: 'tabular-nums' }}>
            {percentLabel(sector.change_1d)}
          </Typography>
        </Stack>
        <Typography sx={{ fontSize: 10.5, color: s.sub, fontVariantNumeric: 'tabular-nums' }} noWrap>
          1W {percentLabel(sector.change_1w)} · 1M {percentLabel(sector.change_1m)}
        </Typography>
      </Box>
    </Tooltip>
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

  const freshPayload = heatmapQuery.data?.data;
  const hasFresh = !!freshPayload?.sectors?.length;

  // Keep the last successful (non-empty) payload so a transient feed outage
  // degrades to "stale but real" data instead of a blank panel. We never
  // fabricate sector values.
  const lastGoodRef = React.useRef<{ payload: NonNullable<typeof freshPayload>; receivedAt: Date } | null>(null);
  if (hasFresh && freshPayload) {
    lastGoodRef.current = { payload: freshPayload, receivedAt: new Date() };
  }

  const payload = hasFresh ? freshPayload : lastGoodRef.current?.payload ?? null;
  const showingStale = !hasFresh && !!lastGoodRef.current;
  const sectors = payload?.sectors ?? [];

  const statusNote = showingStale
    ? `Live feed unavailable — showing last data received ${dayjs(lastGoodRef.current!.receivedAt).format('DD MMM, HH:mm')}`
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
        <Box
          sx={{
            display: 'grid',
            gap: 0.75,
            gridTemplateColumns: { xs: 'repeat(2, 1fr)', sm: 'repeat(3, 1fr)', md: 'repeat(4, 1fr)', lg: 'repeat(6, 1fr)' },
          }}
        >
          {sectors.map((sector) => (
            <HeatmapCard key={sector.symbol} sector={sector} />
          ))}
        </Box>
      ) : (
        <Box sx={{ py: 3, textAlign: 'center' }}>
          <Typography variant="body2" color="text.secondary" gutterBottom>
            Sector data unavailable.
          </Typography>
          <Typography variant="caption" color="text.secondary">
            The heatmap feed returned no sectors and no earlier snapshot exists for this session.
            Check the data pipeline (EOD/intraday scans) or the API health endpoint.
          </Typography>
        </Box>
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
