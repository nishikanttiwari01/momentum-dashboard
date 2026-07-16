import * as React from 'react';
import axios from 'axios';
import { useQuery } from '@tanstack/react-query';
import { Box, Button, Paper, Skeleton, Stack, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material';
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

type MarketKey = 'sensex' | 'sp500';
type Range = '1m' | '6m' | '1y' | '5y';

type HistoryPoint = { on: string; close: number };
type MarketIndexHistory = {
  key: MarketKey;
  name: string;
  symbol: string;
  range: Range;
  latest_value: number;
  change: number;
  change_pct: number;
  points: HistoryPoint[];
};

type Props = { marketKey: MarketKey };

const RANGES: Range[] = ['1m', '6m', '1y', '5y'];
const RANGE_LABEL: Record<Range, string> = { '1m': '1M', '6m': '6M', '1y': '1Y', '5y': '5Y' };
const FALLBACK_NAME: Record<MarketKey, string> = { sensex: 'SENSEX', sp500: 'S&P 500' };
const number = new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const compact = new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 });

function signed(value: number) {
  return `${value >= 0 ? '+' : ''}${number.format(value)}`;
}

function dateTick(value: string) {
  return new Intl.DateTimeFormat('en-US', { month: 'short', year: '2-digit' }).format(new Date(`${value}T00:00:00`));
}

function yDomain(points: HistoryPoint[]): [number, number] {
  if (!points.length) return [0, 1];
  const values = points.map((point) => point.close);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const padding = Math.max((max - min) * 0.12, max * 0.01);
  return [Math.max(0, min - padding), max + padding];
}

const MarketIndexChartCard: React.FC<Props> = ({ marketKey }) => {
  const [range, setRange] = React.useState<Range>('1y');
  const query = useQuery({
    queryKey: ['market-index-history', marketKey, range],
    queryFn: async () =>
      (await axios.get<MarketIndexHistory>(`/api/v1/market-indices/${marketKey}/history`, { params: { range } })).data,
    staleTime: 15 * 60 * 1000,
    retry: 1,
    retryDelay: 0,
  });
  const data = query.data;
  const positive = (data?.change ?? 0) >= 0;

  return (
    <Paper
      data-testid="market-index-chart-card"
      sx={{ p: 2, minHeight: 330, height: '100%', display: 'flex', flexDirection: 'column' }}
    >
      <Stack direction="row" alignItems="flex-start" justifyContent="space-between" spacing={1}>
        <Box sx={{ minWidth: 0 }}>
          {query.isLoading ? (
            <><Skeleton width={150} height={27} /><Skeleton width={110} height={36} /></>
          ) : (
            <>
              <Typography variant="subtitle1" fontWeight={800} noWrap>{data?.name ?? FALLBACK_NAME[marketKey]}</Typography>
              {data ? (
                <Stack direction="row" alignItems="baseline" spacing={1} flexWrap="wrap">
                  <Typography variant="h5" fontWeight={750} sx={{ fontVariantNumeric: 'tabular-nums' }}>
                    {number.format(data.latest_value)}
                  </Typography>
                  <Typography
                    variant="body2"
                    color={positive ? 'success.main' : 'error.main'}
                    fontWeight={700}
                    sx={{ fontVariantNumeric: 'tabular-nums' }}
                  >
                    {signed(data.change)} ({signed(data.change_pct)}%)
                  </Typography>
                </Stack>
              ) : null}
            </>
          )}
        </Box>
        <ToggleButtonGroup
          size="small"
          exclusive
          value={range}
          onChange={(_, value: Range | null) => value && setRange(value)}
          aria-label={`${FALLBACK_NAME[marketKey]} history range`}
        >
          {RANGES.map((item) => (
            <ToggleButton
              key={item}
              value={item}
              aria-label={`Show ${RANGE_LABEL[item]} history`}
              sx={{ px: 0.9, py: 0.2, fontSize: 11, textTransform: 'none' }}
            >
              {RANGE_LABEL[item]}
            </ToggleButton>
          ))}
        </ToggleButtonGroup>
      </Stack>

      <Box sx={{ mt: 1.5, height: 220, flexShrink: 0 }}>
        {query.isLoading ? (
          <Skeleton variant="rounded" height="100%" />
        ) : query.isError ? (
          <Stack alignItems="center" justifyContent="center" spacing={1} sx={{ height: '100%' }}>
            <Typography variant="body2" color="text.secondary">Market index unavailable</Typography>
            <Button
              size="small"
              variant="outlined"
              onClick={() => query.refetch()}
              aria-label={`Retry loading ${FALLBACK_NAME[marketKey]} market index`}
            >
              Retry
            </Button>
          </Stack>
        ) : data && data.points.length ? (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data.points} margin={{ top: 8, right: 12, bottom: 2, left: 6 }}>
              <CartesianGrid vertical={false} stroke="#E9EEF5" strokeDasharray="3 3" />
              <XAxis dataKey="on" tickFormatter={dateTick} minTickGap={42} tick={{ fontSize: 11, fill: '#667085' }} axisLine={false} tickLine={false} />
              <YAxis domain={yDomain(data.points)} tickFormatter={(value) => compact.format(value)} tickCount={5} width={48} tick={{ fontSize: 11, fill: '#667085' }} axisLine={false} tickLine={false} />
              <Tooltip
                labelFormatter={(label) => new Intl.DateTimeFormat('en-US', { dateStyle: 'medium' }).format(new Date(`${label}T00:00:00`))}
                formatter={(value) => [number.format(Number(value)), data.symbol]}
              />
              <Line type="monotone" dataKey="close" stroke="#2874D0" strokeWidth={2} dot={false} activeDot={{ r: 3 }} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <Stack alignItems="center" justifyContent="center" sx={{ height: '100%' }}>
            <Typography variant="body2" color="text.secondary">Market index unavailable</Typography>
          </Stack>
        )}
      </Box>
    </Paper>
  );
};

export default MarketIndexChartCard;
