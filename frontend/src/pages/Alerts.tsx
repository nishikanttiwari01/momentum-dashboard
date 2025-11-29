import * as React from 'react';
import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';
import timezone from 'dayjs/plugin/timezone';
import {
  Alert as MuiAlert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Divider,
  Drawer,
  IconButton,
  Paper,
  Skeleton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import NotificationsActiveIcon from '@mui/icons-material/NotificationsActive';
import MailOutlineIcon from '@mui/icons-material/MailOutline';
import HttpIcon from '@mui/icons-material/Http';

import { useAlerts, type AlertEventListItem } from '@/lib/hooks';
import type { ListAlertEventsParams } from '@/lib/api/types';

dayjs.extend(utc);
dayjs.extend(timezone);

const CHANNEL_ICONS: Record<
  string,
  { icon: React.ReactElement; label: string }
> = {
  ntfy: { icon: <NotificationsActiveIcon fontSize='small' />, label: 'ntfy' },
  email: { icon: <MailOutlineIcon fontSize='small' />, label: 'Email' },
  webhook: { icon: <HttpIcon fontSize='small' />, label: 'Webhook' },
};

const STATUS_COLORS: Record<string, string> = {
  SENT: 'success.main',
  FAILED: 'error.main',
  SKIPPED: 'text.secondary',
};

const STATUS_LABELS: Record<string, string> = {
  SENT: 'Delivered',
  FAILED: 'Failed',
  SKIPPED: 'Skipped',
};

const MODE_LABELS: Record<string, string> = {
  EOD: 'EOD',
  INTRADAY: 'Intraday',
};

export default function Alerts() {
  const today = React.useMemo(() => dayjs().format('YYYY-MM-DD'), []);
  const tz = React.useMemo(() => (typeof dayjs.tz === 'function' ? dayjs.tz.guess() : 'UTC'), []);

  const [selectedDate, setSelectedDate] = React.useState<string | null>(today);
  const [selectedEvent, setSelectedEvent] = React.useState<AlertEventListItem | null>(null);

  const queryParams = React.useMemo<ListAlertEventsParams | undefined>(() => {
    if (!selectedDate) return undefined;
    return { trading_date: selectedDate };
  }, [selectedDate]);

  const {
    data: alerts = [],
    isLoading,
    isFetching,
    isError,
    error,
    refetch,
    dataUpdatedAt,
  } = useAlerts(queryParams, { staleTimeMs: 60_000 });

  const lastUpdatedLabel = React.useMemo(() => {
    if (!dataUpdatedAt) return null;
    return dayjs(dataUpdatedAt).tz(tz).format('YYYY-MM-DD HH:mm:ss');
  }, [dataUpdatedAt, tz]);

  const handleRefresh = React.useCallback(() => {
    refetch();
  }, [refetch]);

  const handleShift = React.useCallback(
    (delta: number) => {
      setSelectedDate((prev) => {
        const base = prev ?? today;
        return dayjs(base).add(delta, 'day').format('YYYY-MM-DD');
      });
    },
    [today],
  );

  const handleDateChange = React.useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    const value = event.target.value;
    setSelectedDate(value ? dayjs(value).format('YYYY-MM-DD') : null);
  }, []);

  const handleToday = React.useCallback(() => {
    setSelectedDate(today);
  }, [today]);

  const handleClear = React.useCallback(() => {
    setSelectedDate(null);
  }, []);

  const showSkeleton = isLoading && alerts.length === 0;
  const showEmpty = !isLoading && alerts.length === 0 && !isError;

  return (
    <Paper sx={{ p: 2, width: '100%' }} elevation={1}>
      <Header
        tz={tz}
        lastUpdatedLabel={lastUpdatedLabel}
        totalCount={alerts.length}
        selectedDate={selectedDate}
        onRefresh={handleRefresh}
        isRefreshing={isFetching}
      />

      <Divider sx={{ my: 2 }} />

      <FilterBar
        selectedDate={selectedDate}
        onShift={handleShift}
        onDateChange={handleDateChange}
        onToday={handleToday}
        onClear={handleClear}
        today={today}
      />

      {isError ? (
        <Box sx={{ mt: 3 }}>
          <MuiAlert severity='error'>
            {error instanceof Error ? error.message : 'Failed to load alert events.'}
          </MuiAlert>
        </Box>
      ) : null}

      {showSkeleton ? (
        <AlertsSkeleton />
      ) : showEmpty ? (
        <AlertsEmptyState selectedDate={selectedDate} />
      ) : (
        <AlertsTable
          alerts={alerts}
          tz={tz}
          onSelect={setSelectedEvent}
          selectedId={selectedEvent?.id ?? null}
        />
      )}

      <AlertDetailsDrawer
        alert={selectedEvent}
        onClose={() => setSelectedEvent(null)}
        tz={tz}
      />
    </Paper>
  );
}

type HeaderProps = {
  tz: string;
  lastUpdatedLabel: string | null;
  totalCount: number;
  selectedDate: string | null;
  onRefresh: () => void;
  isRefreshing: boolean;
};

function Header({
  tz,
  lastUpdatedLabel,
  totalCount,
  selectedDate,
  onRefresh,
  isRefreshing,
}: HeaderProps) {
  const subtitle = selectedDate
    ? `Showing alert events for ${selectedDate}`
    : 'Showing latest alert events';

  return (
    <Stack
      direction={{ xs: 'column', sm: 'row' }}
      alignItems={{ xs: 'flex-start', sm: 'center' }}
      justifyContent='space-between'
      spacing={1.5}
    >
      <Stack spacing={0.25}>
        <Typography variant='h6'>Alerts</Typography>
        <Typography variant='caption' color='text.secondary'>
          {`${subtitle} | Local timezone: ${tz}${lastUpdatedLabel ? ` | Last refreshed: ${lastUpdatedLabel}` : ''}`}
        </Typography>
      </Stack>
      <Stack direction='row' spacing={1} alignItems='center'>
        <Typography variant='caption' color='text.secondary'>
          {totalCount} {totalCount === 1 ? 'event' : 'events'}
        </Typography>
        <Tooltip title='Refresh'>
          <span>
            <IconButton onClick={onRefresh} disabled={isRefreshing} size='small'>
              {isRefreshing ? <CircularProgress size={18} /> : <RefreshIcon fontSize='small' />}
            </IconButton>
          </span>
        </Tooltip>
      </Stack>
    </Stack>
  );
}

type FilterBarProps = {
  selectedDate: string | null;
  onShift: (delta: number) => void;
  onDateChange: (event: React.ChangeEvent<HTMLInputElement>) => void;
  onToday: () => void;
  onClear: () => void;
  today: string;
};

function FilterBar({ selectedDate, onShift, onDateChange, onToday, onClear, today }: FilterBarProps) {
  const hasDate = selectedDate !== null;
  const isToday = hasDate && selectedDate === today;

  return (
    <Stack
      direction={{ xs: 'column', md: 'row' }}
      spacing={1}
      alignItems={{ xs: 'flex-start', md: 'center' }}
      justifyContent='space-between'
    >
      <Stack direction='row' spacing={1}>
        <Button variant='outlined' size='small' onClick={() => onShift(-1)}>
          Previous
        </Button>
        <Button variant='outlined' size='small' onClick={() => onShift(1)} disabled={!hasDate}>
          Next
        </Button>
        <Button
          variant='outlined'
          size='small'
          onClick={onToday}
          disabled={isToday}
        >
          Today
        </Button>
        <Button variant='outlined' size='small' onClick={onClear} disabled={!hasDate}>
          Clear
        </Button>
      </Stack>
      <Stack direction='row' spacing={0.75} alignItems='center'>
        <Typography variant='caption' color='text.secondary'>
          Trading date
        </Typography>
        <TextField
          type='date'
          size='small'
          value={selectedDate ?? ''}
          onChange={onDateChange}
          InputLabelProps={{ shrink: true }}
          sx={{ width: 200 }}
        />
      </Stack>
    </Stack>
  );
}

type AlertsTableProps = {
  alerts: AlertEventListItem[];
  tz: string;
  onSelect: (item: AlertEventListItem) => void;
  selectedId: number | null;
};

function AlertsTable({ alerts, tz, onSelect, selectedId }: AlertsTableProps) {
  return (
    <Box sx={{ mt: 3, overflowX: 'auto' }}>
      <Table size='small'>
        <TableHead>
          <TableRow>
            <TableCell sx={{ minWidth: 150 }}>Fired / Trading</TableCell>
            <TableCell sx={{ minWidth: 80 }}>Symbol</TableCell>
            <TableCell sx={{ minWidth: 170 }}>Alert</TableCell>
            <TableCell sx={{ minWidth: 96 }}>Severity</TableCell>
            <TableCell sx={{ minWidth: 96 }}>Category</TableCell>
            <TableCell sx={{ minWidth: 110 }}>Mode</TableCell>
            <TableCell align='right' sx={{ minWidth: 80 }}>
              Score
            </TableCell>
            <TableCell align='right' sx={{ minWidth: 100 }}>
              Next Action
            </TableCell>
            <TableCell sx={{ minWidth: 110 }}>Channels</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {alerts.map((item) => {
            const isSelected = selectedId === item.id;
            const intradayLabel = formatIntradayBucketLabel(item.intradayBucketLabel);
            return (
              <TableRow
                key={item.id}
                hover
                selected={isSelected}
                onClick={() => onSelect(item)}
                sx={{ cursor: 'pointer' }}
              >
                <TableCell sx={{ minWidth: 150 }}>
                  <Stack spacing={0.25}>
                    <Typography variant='body2'>
                      <Typography
                        component='span'
                        variant='caption'
                        color='text.secondary'
                        sx={{ mr: 0.75 }}
                      >
                        Fired:
                      </Typography>
                      {formatLocalTime(item.firedAtUtc, tz)}
                    </Typography>
                    <Typography variant='body2'>
                      <Typography
                        component='span'
                        variant='caption'
                        color='text.secondary'
                        sx={{ mr: 0.75 }}
                      >
                        Trading:
                      </Typography>
                      {formatTimeSubtitle(item)}
                    </Typography>
                  </Stack>
                </TableCell>
                <TableCell sx={{ minWidth: 80 }}>
                  <Typography variant='body2' fontWeight={600}>
                    {item.symbol}
                  </Typography>
                  <Typography variant='caption' color='text.secondary'>
                    {item.sendType}
                  </Typography>
                </TableCell>
                <TableCell sx={{ minWidth: 170 }}>
                  <Stack spacing={0.25}>
                    <Typography variant='body2' sx={{ wordBreak: 'break-word' }}>
                      {item.title}
                    </Typography>
                    <Typography variant='caption' color='text.secondary' sx={{ wordBreak: 'break-word' }}>
                      {item.raw.rule_code} · {truncate(item.body, 120)}
                    </Typography>
                  </Stack>
                </TableCell>
                <TableCell sx={{ minWidth: 96 }}>
                  <SeverityChip value={item.severity} />
                </TableCell>
                <TableCell sx={{ minWidth: 96 }}>
                  <Chip
                    size='small'
                    label={item.digestBucket}
                    color={item.digestBucket === 'BUY' ? 'success' : item.digestBucket === 'SELL' ? 'error' : 'default'}
                    variant='outlined'
                  />
                </TableCell>
                <TableCell sx={{ minWidth: 110 }}>
                  <Stack spacing={0.25}>
                    <Typography variant='body2'>{MODE_LABELS[item.mode] ?? item.mode}</Typography>
                    {item.mode === 'INTRADAY' && (intradayLabel || item.bucketOrd != null) ? (
                      <Typography variant='caption' color='text.secondary'>
                        {intradayLabel ?? `Bucket ${item.bucketOrd}`}
                      </Typography>
                    ) : null}
                  </Stack>
                </TableCell>
                <TableCell align='right' sx={{ minWidth: 80 }}>
                  {item.scoreAtFire !== null ? formatNumber(item.scoreAtFire) : '--'}
                </TableCell>
                <TableCell align='right' sx={{ minWidth: 100 }}>
                  {item.nextActionCode ? (
                    <Chip
                      size='small'
                      label={item.nextActionCode}
                      variant='outlined'
                      sx={{ fontFamily: 'monospace' }}
                    />
                  ) : (
                    <Typography variant='body2' color='text.secondary'>
                      --
                    </Typography>
                  )}
                </TableCell>
                <TableCell sx={{ minWidth: 110 }}>
                  <ChannelsSummary summary={item.channelsSummary} />
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </Box>
  );
}

function SeverityChip({ value }: { value: string }) {
  const lower = value.toUpperCase();
  let color: 'default' | 'success' | 'warning' | 'error' | 'info' = 'default';
  if (lower === 'CRITICAL') color = 'error';
  else if (lower === 'WARN') color = 'warning';
  else if (lower === 'INFO') color = 'info';
  return <Chip size='small' label={lower} color={color} variant='outlined' />;
}

function ChannelsSummary({ summary }: { summary: Record<string, { status?: string; attempts?: number | null; code?: number | null; reason?: string | null }> }) {
  const entries = Object.entries(summary);
  if (entries.length === 0) {
    return (
      <Typography variant='body2' color='text.secondary'>
        --
      </Typography>
    );
  }

  return (
    <Stack direction='row' spacing={1} sx={{ flexWrap: 'wrap' }}>
      {entries.map(([channel, info]) => {
        const meta = CHANNEL_ICONS[channel] ?? {
          icon: <NotificationsActiveIcon fontSize='small' />,
          label: channel,
        };
        const status = (info?.status ?? 'UNKNOWN').toUpperCase();
        const color = STATUS_COLORS[status] ?? 'text.secondary';
        const reason = info?.reason;
        const attempts = info?.attempts ?? null;
        const code = info?.code ?? null;
        const tooltip = [
          `${meta.label}: ${STATUS_LABELS[status] ?? status}`,
          attempts ? `Attempts: ${attempts}` : null,
          code ? `Code: ${code}` : null,
          reason ? `Reason: ${reason}` : null,
        ]
          .filter(Boolean)
          .join('\n');

        return (
          <Tooltip key={channel} title={tooltip}>
            <Box
              sx={{
                display: 'inline-flex',
                alignItems: 'center',
                px: 0.75,
                py: 0.25,
                borderRadius: 1,
                border: '1px solid',
                borderColor: 'divider',
                color,
                fontSize: '0.75rem',
                gap: 0.5,
              }}
            >
              {React.cloneElement(meta.icon, { sx: { color } })}
              <span>{meta.label}</span>
            </Box>
          </Tooltip>
        );
      })}
    </Stack>
  );
}

function formatLocalTime(iso: string, tz: string): string {
  const parsed = dayjs(iso);
  if (!parsed.isValid()) return iso;
  return parsed.tz(tz).format('YYYY-MM-DD HH:mm');
}

function formatIntradayBucketLabel(label?: string | null): string | null {
  if (!label) return null;
  const trimmed = `${label}`.trim();
  if (/^\d{3,4}$/.test(trimmed)) {
    const padded = trimmed.padStart(4, '0');
    return `${padded.slice(0, 2)}:${padded.slice(2)}`;
  }
  return trimmed;
}

function formatNumber(value: number, fractionDigits = 2): string {
  if (!Number.isFinite(value)) {
    return String(value);
  }
  return value.toFixed(fractionDigits);
}

function formatTimeSubtitle(item: AlertEventListItem): string {
  const parts = [item.tradingDate];
  if (item.mode === 'INTRADAY') {
    const intradayLabel = formatIntradayBucketLabel(item.intradayBucketLabel);
    if (intradayLabel) {
      parts.push(intradayLabel);
    }
  }
  return parts.filter(Boolean).join(' | ');
}

function truncate(text: string, limit: number): string {
  if (text.length <= limit) return text;
  return `${text.slice(0, limit)}…`;
}

function AlertsSkeleton() {
  return (
    <Box sx={{ mt: 3 }}>
      {[1, 2, 3, 4, 5].map((key) => (
        <Skeleton
          key={key}
          variant='rectangular'
          height={48}
          animation='wave'
          sx={{ mb: 1, borderRadius: 1 }}
        />
      ))}
    </Box>
  );
}

function AlertsEmptyState({ selectedDate }: { selectedDate: string | null }) {
  return (
    <Box sx={{ textAlign: 'center', py: 6 }}>
      <Typography variant='subtitle1' color='text.secondary'>
        {selectedDate ? 'No alert events for the selected date.' : 'No alert events recorded yet.'}
      </Typography>
      <Typography variant='body2' color='text.secondary'>
        {selectedDate
          ? 'Adjust the date picker or clear the filter to view more events.'
          : 'Run the alert engine or ingest sample data to populate this view.'}
      </Typography>
    </Box>
  );
}

type AlertDetailsDrawerProps = {
  alert: AlertEventListItem | null;
  onClose: () => void;
  tz: string;
};

function AlertDetailsDrawer({ alert, onClose, tz }: AlertDetailsDrawerProps) {
  return (
    <Drawer
      anchor='right'
      open={Boolean(alert)}
      onClose={onClose}
      PaperProps={{
        sx: {
          mt: { xs: '56px', sm: '64px' },
          height: { xs: 'calc(100% - 56px)', sm: 'calc(100% - 64px)' },
        },
      }}
    >
      <Box
        sx={{
          width: { xs: 320, sm: 380, md: 420 },
          p: 2,
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          gap: 2,
        }}
      >
        {alert ? (
          <>
            <Stack spacing={0.5}>
              <Typography variant='overline' color='text.secondary'>
                {alert.symbol} · {alert.raw.rule_code}
              </Typography>
              <Typography variant='h6'>{alert.title}</Typography>
              <Stack direction='row' spacing={1} alignItems='center' flexWrap='wrap'>
                <SeverityChip value={alert.severity} />
                <Chip size='small' label={alert.digestBucket} variant='outlined' />
                <Chip
                  size='small'
                  label={`${MODE_LABELS[alert.mode] ?? alert.mode}`}
                  variant='outlined'
                />
                {alert.nextActionCode ? (
                  <Chip
                    size='small'
                    label={alert.nextActionCode}
                    variant='outlined'
                    sx={{ fontFamily: 'monospace' }}
                  />
                ) : null}
              </Stack>
              <Typography variant='caption' color='text.secondary'>
                Fired at {formatLocalTime(alert.firedAtUtc, tz)} ({alert.firedAtUtc})
              </Typography>
              <Typography variant='caption' color='text.secondary'>
                Trading date: {alert.tradingDate} · Send type: {alert.sendType}
              </Typography>
              {alert.digestId ? (
                <Typography variant='caption' color='text.secondary'>
                  Digest id: {alert.digestId}
                </Typography>
              ) : null}
            </Stack>

            <Divider />

            <Section title='Body'>
              <Typography variant='body2' sx={{ whiteSpace: 'pre-wrap' }}>
                {alert.body}
              </Typography>
            </Section>

            <Section title='Channels'>
              <ChannelsSummary summary={alert.channelsSummary} />
            </Section>

            <Section title='Context'>
              <KeyValueList data={alert.context} emptyLabel='No context variables.' />
            </Section>

            <Section title='Details'>
              <KeyValueList data={alert.details} emptyLabel='No additional details.' />
            </Section>

            <Section title='Deliveries'>
              <DeliveriesTable deliveries={alert.deliveries} tz={tz} />
            </Section>
          </>
        ) : null}
      </Box>
    </Drawer>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Stack spacing={1}>
      <Typography variant='subtitle2'>{title}</Typography>
      {children}
    </Stack>
  );
}

function KeyValueList({
  data,
  emptyLabel,
}: {
  data: Record<string, unknown>;
  emptyLabel: string;
}) {
  const entries = Object.entries(data);
  if (entries.length === 0) {
    return (
      <Typography variant='body2' color='text.secondary'>
        {emptyLabel}
      </Typography>
    );
  }
  return (
    <Stack spacing={0.5}>
      {entries.map(([key, value]) => (
        <Stack key={key} direction='row' spacing={1} alignItems='flex-start'>
          <Typography
            variant='body2'
            sx={{ minWidth: 96, fontWeight: 500, color: 'text.secondary' }}
          >
            {key}
          </Typography>
          <Typography variant='body2' sx={{ wordBreak: 'break-word' }}>
            {formatValue(value)}
          </Typography>
        </Stack>
      ))}
    </Stack>
  );
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '-';
  if (typeof value === 'string') return value;
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return '-';
    return Number.isInteger(value) ? value.toString() : formatNumber(value);
  }
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  try {
    return JSON.stringify(value, null, 2);
  } catch (err) {
    return String(value);
  }
}

function DeliveriesTable({
  deliveries,
  tz,
}: {
  deliveries: AlertEventListItem['deliveries'];
  tz: string;
}) {
  if (!deliveries || deliveries.length === 0) {
    return (
      <Typography variant='body2' color='text.secondary'>
        No delivery attempts recorded.
      </Typography>
    );
  }
  return (
    <Stack spacing={1}>
      {deliveries.map((delivery, idx) => (
        <Box
          key={`${delivery.channel}-${delivery.attempt_no}-${idx}`}
          sx={{
            border: '1px solid',
            borderColor: 'divider',
            borderRadius: 1,
            p: 1,
          }}
        >
          <Stack direction='row' spacing={1} alignItems='center'>
            <Typography variant='body2' fontWeight={600}>
              {delivery.channel ?? 'unknown'}
            </Typography>
            <Chip
              size='small'
              label={delivery.status ?? 'UNKNOWN'}
              color={
                delivery.status === 'SENT'
                  ? 'success'
                  : delivery.status === 'FAILED'
                  ? 'error'
                  : 'default'
              }
              variant='outlined'
            />
            <Typography variant='caption' color='text.secondary'>
              Attempt #{delivery.attempt_no ?? '?'}
            </Typography>
          </Stack>
          <Typography variant='caption' color='text.secondary'>
            Sent at:{' '}
            {delivery.sent_at_utc
              ? `${formatLocalTime(delivery.sent_at_utc, tz)} (${delivery.sent_at_utc})`
              : '—'}
          </Typography>
          {delivery.response_code ? (
            <Typography variant='caption' color='text.secondary'>
              Response code: {delivery.response_code}
            </Typography>
          ) : null}
          {delivery.response_meta && Object.keys(delivery.response_meta).length > 0 ? (
            <Typography variant='caption' color='text.secondary' sx={{ display: 'block', mt: 0.5 }}>
              Meta: {JSON.stringify(delivery.response_meta)}
            </Typography>
          ) : null}
        </Box>
      ))}
    </Stack>
  );
}
