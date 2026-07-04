import React from 'react';
import axios from 'axios';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  Stack,
  Typography,
} from '@mui/material';

type TriggerState = 'idle' | 'running' | 'success' | 'error';
type Channel = 'email' | 'ntfy' | 'windows_toast';

interface TestAlertResult {
  channel: Channel;
  status: string;             // SENT | FAILED | SKIPPED
  code?: number | null;
  reason?: string;
  meta?: Record<string, unknown>;
  to?: string[];
  topic?: string;
  server?: string;
}

const CHANNEL_LABEL: Record<Channel, string> = {
  email: 'Email',
  ntfy: 'ntfy (push)',
  windows_toast: 'Windows Toast + Sound',
};

const CHANNEL_DESC: Record<Channel, string> = {
  email: 'Sends a test email to the configured recipients via the SMTP credentials in alerts.yaml.',
  ntfy: 'Publishes a test message to the configured ntfy topic — check the ntfy app on your phone.',
  windows_toast: 'Pops a Windows 10/11 toast with a system sound on this machine. Requires Windows host.',
};

function statusColor(status: string | undefined): 'success' | 'error' | 'warning' | 'default' {
  if (!status) return 'default';
  if (status === 'SENT') return 'success';
  if (status === 'FAILED') return 'error';
  if (status === 'SKIPPED') return 'warning';
  return 'default';
}

export default function Settings() {
  const [eodState, setEodState] = React.useState<TriggerState>('idle');
  const [eodError, setEodError] = React.useState<string | null>(null);

  const [testState, setTestState] = React.useState<Record<Channel, TriggerState>>({
    email: 'idle',
    ntfy: 'idle',
    windows_toast: 'idle',
  });
  const [testResult, setTestResult] = React.useState<Record<Channel, TestAlertResult | null>>({
    email: null,
    ntfy: null,
    windows_toast: null,
  });
  const [testError, setTestError] = React.useState<Record<Channel, string | null>>({
    email: null,
    ntfy: null,
    windows_toast: null,
  });

  const triggerEod = React.useCallback(async () => {
    setEodState('running');
    setEodError(null);
    try {
      await axios.post('/api/v1/settings/run-eod');
      setEodState('success');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to trigger EOD run';
      setEodError(message);
      setEodState('error');
    }
  }, []);

  const fireTest = React.useCallback(async (channel: Channel) => {
    setTestState((s) => ({ ...s, [channel]: 'running' }));
    setTestError((s) => ({ ...s, [channel]: null }));
    setTestResult((s) => ({ ...s, [channel]: null }));
    try {
      const resp = await axios.post<TestAlertResult>(
        '/api/v1/settings/test-alert',
        { channel },
      );
      setTestResult((s) => ({ ...s, [channel]: resp.data }));
      const ok = resp.data.status === 'SENT';
      setTestState((s) => ({ ...s, [channel]: ok ? 'success' : 'error' }));
      if (!ok) {
        setTestError((s) => ({
          ...s,
          [channel]: resp.data.reason
            || (resp.data.meta && typeof resp.data.meta === 'object'
                ? JSON.stringify(resp.data.meta)
                : `Status: ${resp.data.status}`),
        }));
      }
    } catch (err) {
      const msg = axios.isAxiosError(err)
        ? (err.response?.data?.detail || err.message)
        : (err instanceof Error ? err.message : 'Request failed');
      setTestError((s) => ({ ...s, [channel]: String(msg) }));
      setTestState((s) => ({ ...s, [channel]: 'error' }));
    }
  }, []);

  return (
    <Box sx={{ px: 3, py: 2, maxWidth: 900 }}>
      <Typography variant="h5" fontWeight={800} gutterBottom>
        Settings
      </Typography>

      {/* Daily EOD card */}
      <Card elevation={0} sx={{ border: '1px solid', borderColor: 'divider', mb: 2 }}>
        <CardContent>
          <Stack spacing={2}>
            <Box>
              <Typography variant="h6" fontWeight={700}>
                Daily EOD
              </Typography>
            </Box>

            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems="center">
              <Button
                variant="contained"
                onClick={triggerEod}
                disabled={eodState === 'running'}
              >
                {eodState === 'running' ? 'Triggering...' : 'Trigger Daily EOD'}
              </Button>
              <Typography variant="body2" color="text.secondary">
                Runs in the background; check logs for progress.
              </Typography>
            </Stack>

            {eodState === 'success' && (
              <Alert severity="success">Daily EOD backfill was started.</Alert>
            )}
            {eodState === 'error' && (
              <Alert severity="error">{eodError || 'Unable to start the EOD run.'}</Alert>
            )}
          </Stack>
        </CardContent>
      </Card>

      {/* Test alerts card */}
      <Card elevation={0} sx={{ border: '1px solid', borderColor: 'divider' }}>
        <CardContent>
          <Stack spacing={2}>
            <Box>
              <Typography variant="h6" fontWeight={700}>
                Test Alerts
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Fire a fake alert through each channel to verify delivery. Test
                alerts bypass dedupe, cooldowns, and rate limits — click as often
                as you need. They are not saved to the alert history.
              </Typography>
            </Box>

            <Divider />

            {(['email', 'ntfy', 'windows_toast'] as Channel[]).map((channel) => {
              const state = testState[channel];
              const result = testResult[channel];
              const errMsg = testError[channel];
              return (
                <Box key={channel}>
                  <Stack
                    direction={{ xs: 'column', sm: 'row' }}
                    spacing={1.5}
                    alignItems={{ xs: 'flex-start', sm: 'center' }}
                  >
                    <Button
                      variant="outlined"
                      onClick={() => fireTest(channel)}
                      disabled={state === 'running'}
                      sx={{ minWidth: 200 }}
                    >
                      {state === 'running'
                        ? `Sending ${CHANNEL_LABEL[channel]}...`
                        : `Send test ${CHANNEL_LABEL[channel]}`}
                    </Button>
                    <Typography variant="body2" color="text.secondary">
                      {CHANNEL_DESC[channel]}
                    </Typography>
                    {result?.status && (
                      <Chip
                        label={result.status}
                        color={statusColor(result.status)}
                        size="small"
                      />
                    )}
                  </Stack>

                  {state === 'success' && result?.status === 'SENT' && (
                    <Alert severity="success" sx={{ mt: 1 }}>
                      {channel === 'email' && result.to?.length
                        ? `Email sent to ${result.to.join(', ')}.`
                        : channel === 'ntfy'
                          ? `Published to topic "${result.topic}" on ${result.server}.`
                          : 'Toast fired — check your desktop for the popup.'}
                    </Alert>
                  )}

                  {(state === 'error' || result?.status === 'SKIPPED' || result?.status === 'FAILED') && (
                    <Alert
                      severity={result?.status === 'SKIPPED' ? 'warning' : 'error'}
                      sx={{ mt: 1 }}
                    >
                      {errMsg
                        || result?.reason
                        || `Channel ${CHANNEL_LABEL[channel]} did not send.`}
                    </Alert>
                  )}
                </Box>
              );
            })}
          </Stack>
        </CardContent>
      </Card>
    </Box>
  );
}
