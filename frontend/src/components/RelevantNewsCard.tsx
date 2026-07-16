import * as React from 'react';
import { Box, Chip, Link as MuiLink, Paper, Stack, Typography } from '@mui/material';
import { Link } from 'react-router-dom';
import axios from 'axios';
import dayjs from 'dayjs';
import { useQuery } from '@tanstack/react-query';

type NewsItem = {
  headline?: string;
  title?: string;
  url?: string;
  link?: string;
  source?: string;
  published_at?: string;
  published?: string;
  summary?: string | null;
};

type SymbolNews = {
  symbol: string;
  why: 'positions' | 'candidates';
  items: NewsItem[];
};

type RelevantNews = {
  generated_at: string;
  window_days: number;
  symbols: SymbolNews[];
  total_items: number;
};

const WHY_LABEL: Record<string, string> = {
  positions: 'holding',
  candidates: 'candidate',
};

const itemTitle = (n: NewsItem) => n.headline ?? n.title ?? 'Untitled';
const itemUrl = (n: NewsItem) => n.url ?? n.link ?? undefined;
const itemTime = (n: NewsItem) => n.published_at ?? n.published ?? undefined;

const RelevantNewsCard: React.FC = () => {
  const query = useQuery({
    queryKey: ['relevant-news'],
    queryFn: async () => (await axios.get<RelevantNews>('/api/v1/news/relevant')).data,
    staleTime: 10 * 60 * 1000,
    retry: 1,
  });

  const data = query.data;
  if (query.isError) return null;

  const withNews = (data?.symbols ?? []).filter((s) => s.items.length > 0);

  return (
    <Paper sx={{ p: 2 }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 800, letterSpacing: '.02em' }}>
          News on my holdings &amp; watchlist
        </Typography>
        <MuiLink component={Link} to="/news" variant="caption">
          All news →
        </MuiLink>
      </Stack>

      {query.isLoading ? (
        <Typography variant="caption" color="text.secondary">
          Checking news…
        </Typography>
      ) : withNews.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          No recent news for your positions or candidates
          {data ? ` (last ${data.window_days} days)` : ''}. News ingestion may still be warming up —
          check the Data Health strip.
        </Typography>
      ) : (
        <Stack spacing={1.25}>
          {withNews.map((s) => (
            <Box key={s.symbol}>
              <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.25 }}>
                <Typography variant="body2" fontWeight={700}>
                  {s.symbol.replace('.NS', '')}
                </Typography>
                <Chip size="small" variant="outlined" label={WHY_LABEL[s.why] ?? s.why} />
              </Stack>
              {s.items.slice(0, 3).map((n, idx) => (
                <Box key={idx} sx={{ pl: 1, display: 'flex', gap: 1, alignItems: 'baseline', flexWrap: 'wrap' }}>
                  {itemUrl(n) ? (
                    <MuiLink href={itemUrl(n)} target="_blank" rel="noopener" variant="body2">
                      {itemTitle(n)}
                    </MuiLink>
                  ) : (
                    <Typography variant="body2">{itemTitle(n)}</Typography>
                  )}
                  <Typography variant="caption" color="text.secondary">
                    {n.source ?? ''}
                    {itemTime(n) ? ` • ${dayjs(itemTime(n)).format('DD MMM, HH:mm')}` : ''}
                  </Typography>
                </Box>
              ))}
            </Box>
          ))}
        </Stack>
      )}
    </Paper>
  );
};

export default RelevantNewsCard;
