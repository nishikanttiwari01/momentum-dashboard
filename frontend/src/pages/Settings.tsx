import React from 'react';
import axios from 'axios';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Stack,
  Typography,
} from '@mui/material';

type TriggerState = 'idle' | 'running' | 'success' | 'error';

export default function Settings() {
  const [state, setState] = React.useState<TriggerState>('idle');
  const [error, setError] = React.useState<string | null>(null);

  const triggerEod = React.useCallback(async () => {
    setState('running');
    setError(null);
    try {
      await axios.post('/api/v1/settings/run-eod');
      setState('success');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to trigger EOD run';
      setError(message);
      setState('error');
    }
  }, []);

  return (
    <Box sx={{ px: 3, py: 2, maxWidth: 900 }}>
      <Typography variant="h5" fontWeight={800} gutterBottom>
        Settings
      </Typography>

      <Card elevation={0} sx={{ border: '1px solid', borderColor: 'divider' }}>
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
                disabled={state === 'running'}
              >
                {state === 'running' ? 'Triggering...' : 'Trigger Daily EOD'}
              </Button>
              <Typography variant="body2" color="text.secondary">
                Runs in the background; check logs for progress.
              </Typography>
            </Stack>

            {state === 'success' && (
              <Alert severity="success">
                Daily EOD backfill was started.
              </Alert>
            )}
            {state === 'error' && (
              <Alert severity="error">
                {error || 'Unable to start the EOD run.'}
              </Alert>
            )}
          </Stack>
        </CardContent>
      </Card>
    </Box>
  );
}
