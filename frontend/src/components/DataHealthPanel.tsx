import * as React from 'react';
import { Box, Chip, Paper, Stack, Tooltip, Typography } from '@mui/material';
import axios from 'axios';
import dayjs from 'dayjs';
import { useQuery } from '@tanstack/react-query';

type DatasetStatus = {
  name: string;
  exists: boolean;
  last_updated: string | null;
  age_hours: number | null;
};

type DataHealthResponse = {
  generated_at: string;
  adapter: string | null;
  news_enabled: boolean;
  timezone: string | null;
  datasets: DatasetStatus[];
  candidate_pool: {
    active: number | null;
    stale: number | null;
    oldest_age_days: number | null;
  };
};

// Freshness thresholds (hours) per dataset before we flag it.
const STALE_AFTER_HOURS: Record<string, number> = {
  prices: 30,
  scores: 30,
  indicators: 30,
  universe: 24 * 8,
  news: 24,
};

const datasetTone = (d: DatasetStatus): 'success' | 'warning' | 'default' => {
  // Empty dataset = not part of this pipeline yet; informational, not an alarm.
  if (!d.exists || d.last_updated == null) return 'default';
  const limit = STALE_AFTER_HOURS[d.name] ?? 30;
  if (d.age_hours != null && d.age_hours > limit) return 'warning';
  return 'success';
};

const datasetLabel = (d: DatasetStatus): string => {
  if (!d.exists || d.last_updated == null) return `${d.name}: no data`;
  if (d.age_hours == null) return d.name;
  if (d.age_hours < 1) return `${d.name}: <1h`;
  if (d.age_hours < 48) return `${d.name}: ${Math.round(d.age_hours)}h`;
  return `${d.name}: ${Math.round(d.age_hours / 24)}d`;
};

const DataHealthPanel: React.FC = () => {
  const query = useQuery({
    queryKey: ['data-health'],
    queryFn: async () => {
      const res = await axios.get<DataHealthResponse>('/api/v1/health/data');
      return res.data;
    },
    refetchInterval: 5 * 60 * 1000,
    retry: 1,
  });

  const data = query.data;

  return (
    <Paper sx={{ p: 1.5 }}>
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={1}
        alignItems={{ xs: 'flex-start', sm: 'center' }}
        flexWrap="wrap"
        useFlexGap
      >
        <Typography variant="subtitle2" sx={{ fontWeight: 700, mr: 1 }}>
          Data Health
        </Typography>

        {query.isLoading ? (
          <Typography variant="caption" color="text.secondary">
            Checking…
          </Typography>
        ) : query.isError || !data ? (
          <Chip size="small" color="error" label="Health endpoint unreachable" />
        ) : (
          <>
            {data.datasets.map((d) => (
              <Tooltip
                key={d.name}
                title={
                  d.last_updated
                    ? `Last update: ${dayjs(d.last_updated).format('DD MMM YYYY, HH:mm')}`
                    : 'No data found on disk'
                }
              >
                <Chip size="small" color={datasetTone(d)} variant="outlined" label={datasetLabel(d)} />
              </Tooltip>
            ))}

            {data.candidate_pool.active != null ? (
              <Tooltip
                title={`Active candidates: ${data.candidate_pool.active}${
                  data.candidate_pool.oldest_age_days != null
                    ? ` • oldest ${data.candidate_pool.oldest_age_days}d`
                    : ''
                }`}
              >
                <Chip
                  size="small"
                  variant="outlined"
                  color={data.candidate_pool.stale ? 'warning' : 'success'}
                  label={
                    data.candidate_pool.stale
                      ? `pool: ${data.candidate_pool.stale} stale`
                      : `pool: ${data.candidate_pool.active} active`
                  }
                />
              </Tooltip>
            ) : null}

            <Chip
              size="small"
              variant="outlined"
              color={data.news_enabled ? 'success' : 'default'}
              label={data.news_enabled ? 'news: on' : 'news: off'}
            />

            {data.adapter ? (
              <Chip size="small" variant="outlined" label={`source: ${data.adapter}`} />
            ) : null}

            <Box sx={{ flexGrow: 1 }} />
            <Typography variant="caption" color="text.secondary">
              checked {dayjs(data.generated_at).format('HH:mm')}
            </Typography>
          </>
        )}
      </Stack>
    </Paper>
  );
};

export default DataHealthPanel;
