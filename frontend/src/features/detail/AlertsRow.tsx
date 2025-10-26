import * as React from 'react';
import dayjs from 'dayjs';
import { Box, Chip, Stack, Typography } from '@mui/material';
import type { AlertTemplate, DrawerAlertEvent } from '@/lib/api/types';

const severityColor: Record<string, 'default' | 'primary' | 'success' | 'warning' | 'error'> = {
  INFO: 'primary',
  WARN: 'warning',
  WARNING: 'warning',
  CRITICAL: 'error',
  ERROR: 'error',
  SUCCESS: 'success',
};

const DEFAULT_EVENTS_FALLBACK: Array<{ key: string; label: string }> = [
  { key: 'no-alerts', label: 'No alerts in the last 7 days' },
];

type Props = {
  templates?: AlertTemplate[] | null;
  events?: DrawerAlertEvent[] | null;
};

export default function AlertsRow({ templates, events }: Props) {
  const eventItems = React.useMemo(() => {
    if (!Array.isArray(events) || events.length === 0) return [];
    return events
      .filter((event): event is DrawerAlertEvent => Boolean(event && event.id))
      .slice(0, 8);
  }, [events]);

  if (eventItems.length > 0) {
    return (
      <Stack spacing={1.25}>
        {eventItems.map((event) => {
          const severity = (event.severity || 'INFO').toUpperCase();
          const chipColor = severityColor[severity] ?? 'primary';
          const firedLabel = event.fired_at_utc
            ? dayjs(event.fired_at_utc).format('DD MMM, HH:mm')
            : event.trading_day;
          const summaryParts = [
            event.digest_bucket,
            event.mode || 'EOD',
            firedLabel ? `${firedLabel} UTC` : null,
          ].filter(Boolean) as string[];
          const key = `${event.id}-${event.fired_at_utc ?? event.trading_day ?? 'event'}`;

          return (
            <Box
              key={key}
              sx={{
                border: 1,
                borderColor: 'divider',
                borderRadius: 1.5,
                px: 1.5,
                py: 1.25,
                display: 'grid',
                gridTemplateColumns: { xs: '1fr', sm: '1fr auto' },
                gap: 1,
              }}
            >
              <Box>
                <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.25 }}>
                  {event.title || event.rule_code}
                </Typography>
                {event.body ? (
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                    {event.body}
                  </Typography>
                ) : null}
                <Typography variant="caption" color="text.secondary">
                  {summaryParts.join(' | ')}
                </Typography>
              </Box>
              <Stack direction="row" spacing={0.75} alignItems="center" justifyContent="flex-end">
                <Chip size="small" label={severity} color={chipColor} variant="outlined" />
                {typeof event.score_at_fire === 'number' ? (
                  <Typography variant="caption" color="text.secondary">
                    Score {Math.round(event.score_at_fire)}
                  </Typography>
                ) : null}
              </Stack>
            </Box>
          );
        })}
      </Stack>
    );
  }

  const templateItems =
    Array.isArray(templates) && templates.length > 0
      ? templates.map((t, idx) => ({
          key: t?.code ?? t?.label ?? t?.example ?? `alert-${idx}`,
          label: String(t?.label ?? t?.code ?? t?.example ?? 'Alert'),
        }))
      : DEFAULT_EVENTS_FALLBACK;

  return (
    <Stack direction="row" spacing={1} alignItems="center" sx={{ flexWrap: 'wrap' }}>
      {templateItems.map((it) => (
        <Chip key={it.key} size="small" label={it.label} variant="outlined" />
      ))}
    </Stack>
  );
}
