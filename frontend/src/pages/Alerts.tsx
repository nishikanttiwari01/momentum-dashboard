import * as React from 'react';
import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';
import timezone from 'dayjs/plugin/timezone';
import {
  Paper,
  Stack,
  Typography,
  Divider,
  IconButton,
  Tooltip,
  Chip,
  Table,
  TableHead,
  TableBody,
  TableRow,
  TableCell,
  Skeleton,
  Box,
} from '@mui/material';
import MuiAlert from '@mui/material/Alert';
import RefreshIcon from '@mui/icons-material/Refresh';
import NotificationsActiveIcon from '@mui/icons-material/NotificationsActive';
import MailOutlineIcon from '@mui/icons-material/MailOutline';
import DesktopWindowsIcon from '@mui/icons-material/DesktopWindows';
import WhatsAppIcon from '@mui/icons-material/WhatsApp';

import { useAlerts, type AlertListItem, type AlertChannelFlags } from '@/lib/hooks';

dayjs.extend(utc);
dayjs.extend(timezone);

const CHANNEL_ORDER = ['desktop', 'email', 'whatsapp'] as const;

export default function Alerts() {
  const {
    data: alerts = [],
    isLoading,
    isFetching,
    isError,
    refetch,
    error,
    dataUpdatedAt,
  } = useAlerts();

  const tz = React.useMemo(() => {
    if (typeof dayjs.tz === 'function') {
      return dayjs.tz.guess();
    }
    return 'UTC';
  }, []);

  const lastUpdatedLabel = React.useMemo(() => {
    if (!dataUpdatedAt) return null;
    return dayjs(dataUpdatedAt).tz(tz).format('YYYY-MM-DD HH:mm:ss');
  }, [dataUpdatedAt, tz]);

  const handleRefresh = React.useCallback(() => {
    refetch();
  }, [refetch]);

  const showSkeleton = isLoading && alerts.length === 0;
  const showEmpty = !isLoading && alerts.length === 0 && !isError;

  const totalLabel = `${alerts.length} ${alerts.length === 1 ? 'alert' : 'alerts'}`;

  return (
    <Paper sx={{ p: 2, width: '100%' }} elevation={1}>
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        alignItems={{ xs: 'flex-start', sm: 'center' }}
        justifyContent="space-between"
        spacing={1}
      >
        <Stack spacing={0.25}>
          <Typography variant="h6">Alerts</Typography>
          <Typography variant="caption" color="text.secondary">
            Active alert rules and their latest signal state.
          </Typography>
          {lastUpdatedLabel ? (
            <Typography variant="caption" color="text.secondary">
              Last updated: {lastUpdatedLabel} ({tz})
            </Typography>
          ) : null}
        </Stack>
        <Stack direction="row" spacing={1} alignItems="center">
          <Chip
            size="small"
            icon={<NotificationsActiveIcon fontSize="small" />}
            label={totalLabel}
            variant="outlined"
          />
          <Tooltip title="Refresh">
            <span style={{ display: 'inline-flex' }}>
              <IconButton
                size="small"
                aria-label="Refresh alerts"
                onClick={handleRefresh}
                disabled={isFetching}
              >
                <RefreshIcon fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
        </Stack>
      </Stack>

      {isError ? (
        <MuiAlert severity="error" sx={{ mt: 2 }}>
          Failed to load alerts
          {error instanceof Error && error.message ? `: ${error.message}` : ''}
        </MuiAlert>
      ) : null}

      <Divider sx={{ mt: 2, mb: 2 }} />

      {showSkeleton ? (
        <AlertsSkeleton />
      ) : showEmpty ? (
        <AlertsEmptyState />
      ) : (
        <AlertsTable items={alerts} tz={tz} />
      )}
    </Paper>
  );
}

function AlertsTable({ items, tz }: { items: AlertListItem[]; tz: string }) {
  return (
    <Box sx={{ width: '100%', overflowX: 'auto' }}>
      <Table size="small">
        <AlertsTableHead />
        <TableBody>
          {items.map((alert) => {
            const rowKey = alert.id ?? `${alert.symbol}-${alert.label}`;
            return (
              <TableRow key={rowKey}>
                <TableCell sx={{ minWidth: 100 }}>
                  <Typography variant="subtitle2">{alert.symbol || '--'}</Typography>
                </TableCell>
                <TableCell>
                  <Stack spacing={0.5}>
                    <Typography variant="subtitle2">{alert.label}</Typography>
                    {alert.description ? (
                      <Typography variant="body2" color="text.secondary">
                        {alert.description}
                      </Typography>
                    ) : null}
                  </Stack>
                </TableCell>
                <TableCell sx={{ minWidth: 200 }}>
                  <ChannelsCell item={alert} />
                </TableCell>
                <TableCell sx={{ minWidth: 120 }}>
                  <Chip
                    size="small"
                    label={alert.enabled ? 'Enabled' : 'Disabled'}
                    color={alert.enabled ? 'success' : 'default'}
                    variant={alert.enabled ? 'filled' : 'outlined'}
                  />
                </TableCell>
                <TableCell sx={{ minWidth: 160 }}>
                  <Typography variant="body2" color="text.secondary">
                    {formatDate(alert.lastFiredAt, tz)}
                  </Typography>
                </TableCell>
                <TableCell sx={{ minWidth: 160 }}>
                  <Typography variant="body2" color="text.secondary">
                    {formatDate(alert.mutedUntil, tz)}
                  </Typography>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </Box>
  );
}

function AlertsSkeleton() {
  return (
    <Box sx={{ width: '100%', overflowX: 'auto' }}>
      <Table size="small">
        <AlertsTableHead />
        <TableBody>
          {Array.from({ length: 3 }).map((_, rowIdx) => (
            <TableRow key={rowIdx}>
              {Array.from({ length: 6 }).map((__, cellIdx) => (
                <TableCell key={cellIdx}>
                  <Skeleton
                    variant="text"
                    width={cellIdx === 1 ? '80%' : '60%'}
                    height={20}
                  />
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Box>
  );
}

function AlertsEmptyState() {
  return (
    <Box sx={{ textAlign: 'center', py: 6 }}>
      <Typography variant="subtitle1" color="text.secondary">
        No alerts configured yet.
      </Typography>
      <Typography variant="body2" color="text.secondary">
        Add a rule to start receiving notifications.
      </Typography>
    </Box>
  );
}

function AlertsTableHead() {
  return (
    <TableHead>
      <TableRow>
        <TableCell sx={{ minWidth: 100 }}>Symbol</TableCell>
        <TableCell>Rule</TableCell>
        <TableCell sx={{ minWidth: 200 }}>Channels</TableCell>
        <TableCell sx={{ minWidth: 120 }}>Status</TableCell>
        <TableCell sx={{ minWidth: 160 }}>Last Signal</TableCell>
        <TableCell sx={{ minWidth: 160 }}>Muted</TableCell>
      </TableRow>
    </TableHead>
  );
}

function ChannelsCell({ item }: { item: AlertListItem }) {
  const keys = getSortedChannelKeys(item.channelFlags);
  if (keys.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        --
      </Typography>
    );
  }

  return (
    <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap' }}>
      {keys.map((key) => {
        const icon = getChannelIcon(key);
        return (
          <Chip
            key={key}
            size="small"
            icon={icon}
            label={formatChannelLabel(key)}
            variant="outlined"
          />
        );
      })}
    </Stack>
  );
}

function getSortedChannelKeys(flags: AlertChannelFlags): string[] {
  const keys = Object.entries(flags)
    .filter(([, active]) => active)
    .map(([key]) => key);

  return keys.sort((a, b) => {
    const aIndex = CHANNEL_ORDER.indexOf(a as (typeof CHANNEL_ORDER)[number]);
    const bIndex = CHANNEL_ORDER.indexOf(b as (typeof CHANNEL_ORDER)[number]);
    if (aIndex === -1 && bIndex === -1) {
      return a.localeCompare(b);
    }
    if (aIndex === -1) return 1;
    if (bIndex === -1) return -1;
    return aIndex - bIndex;
  });
}

function getChannelIcon(key: string) {
  switch (key) {
    case 'desktop':
      return <DesktopWindowsIcon fontSize="small" />;
    case 'email':
      return <MailOutlineIcon fontSize="small" />;
    case 'whatsapp':
      return <WhatsAppIcon fontSize="small" />;
    default:
      return undefined;
  }
}

function formatChannelLabel(key: string): string {
  return key
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function formatDate(value: string | null, tz: string): string {
  if (!value) return '--';
  const parsed = dayjs(value);
  if (parsed.isValid()) {
    return parsed.tz(tz).format('YYYY-MM-DD HH:mm');
  }
  const numeric = Number(value);
  if (Number.isFinite(numeric)) {
    const asDate = dayjs(numeric);
    if (asDate.isValid()) {
      return asDate.tz(tz).format('YYYY-MM-DD HH:mm');
    }
  }
  return value;
}
