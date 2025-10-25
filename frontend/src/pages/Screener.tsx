import * as React from 'react';
import { useOutletContext } from 'react-router-dom';
import type { OutletCtx } from '../layouts/AppShell';
import {
  Box,
  Button,
  CircularProgress,
  Divider,
  FormControl,
  InputLabel,
  Menu,
  MenuItem,
  Paper,
  Select,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';
import type { SelectChangeEvent } from '@mui/material/Select';
import DownloadIcon from '@mui/icons-material/Download';
import MomentumTable from '../components/MomentumTable';
import { useGetScreenerRunDates, useGetScreenerRuns } from '@/lib/api/client';
import type { ScreenerRunSummary } from '@/lib/api/types';

const MODE_INTRADAY = 'intraday' as const;
const MODE_EOD = 'eod' as const;
type Mode = typeof MODE_INTRADAY | typeof MODE_EOD;

export default function Screener() {
  const { refetchIntervalMs } = useOutletContext<OutletCtx>();
  const [tickerInput, setTickerInput] = React.useState('');
  const [symbolFilter, setSymbolFilter] = React.useState<string | undefined>(undefined);

  const [pendingMode, setPendingMode] = React.useState<Mode>(MODE_INTRADAY);
  const [pendingDate, setPendingDate] = React.useState<string | undefined>(undefined);
  const [pendingRun, setPendingRun] = React.useState<ScreenerRunSummary | null>(null);

  const [appliedMode, setAppliedMode] = React.useState<Mode>(MODE_INTRADAY);
  const [appliedRunId, setAppliedRunId] = React.useState<string | undefined>(undefined);
  const [appliedAsOf, setAppliedAsOf] = React.useState<string | undefined>(undefined);
  const [hasAppliedInitial, setHasAppliedInitial] = React.useState(false);

  const [exportAnchorEl, setExportAnchorEl] = React.useState<HTMLElement | null>(null);
  const [isExporting, setIsExporting] = React.useState(false);

  // Guard to avoid clearing date/run during programmatic initial seeding
  const suppressModeResetRef = React.useRef(false);

  const handleTickerSubmit = React.useCallback((event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const value = tickerInput.trim();
    if (!value) {
      setSymbolFilter(undefined);
      setTickerInput('');
      return;
    }
    const normalized = value.toUpperCase();
    setSymbolFilter(normalized);
    setTickerInput(normalized);
  }, [tickerInput]);

  const handleClear = React.useCallback(() => {
    setTickerInput('');
    setSymbolFilter(undefined);
  }, []);

  // Reset date/run when user manually switches mode (unless suppressed by initial seeding)
  React.useEffect(() => {
    if (suppressModeResetRef.current) {
      suppressModeResetRef.current = false;
      return;
    }
    setPendingDate(undefined);
    setPendingRun(null);
  }, [pendingMode]);

  // Fetch available dates per mode
  const runDatesQuery = useGetScreenerRunDates(
    { mode: pendingMode, limit: 60 },
    { query: { keepPreviousData: true } },
  );
  const runDatesPayload = runDatesQuery.data?.data;

  const availableDates = React.useMemo(() => {
    const dates = runDatesPayload?.dates ?? [];
    return dates
      .map((item) => {
        const value = pendingMode === MODE_INTRADAY ? item.trade_date : item.as_of;
        if (!value) return null;
        return { value, label: item.label ?? value };
      })
      .filter((item): item is { value: string; label: string } => Boolean(item));
  }, [runDatesPayload, pendingMode]);

  // If no date yet, pick a sensible default from run-dates for the chosen mode
  React.useEffect(() => {
    if (availableDates.length === 0) {
      return;
    }
    const values = availableDates.map((d) => d.value);
    const preferred = pendingMode === MODE_INTRADAY
      ? runDatesPayload?.latest?.trade_date
      : runDatesPayload?.latest?.as_of;
    const fallback = preferred && values.includes(preferred) ? preferred : values[0];
    if (!pendingDate) {
      setPendingDate(fallback);
    }
  }, [availableDates, pendingMode, pendingDate, runDatesPayload]);

  // Fetch run list for the selected date/mode
  const runListParams = React.useMemo(() => {
    if (!pendingDate) return undefined;
    if (pendingMode === MODE_INTRADAY) {
      return { mode: pendingMode, trade_date: pendingDate, limit: 25 } as const;
    }
    return { mode: pendingMode, as_of: pendingDate } as const;
  }, [pendingMode, pendingDate]);

  const runListQuery = useGetScreenerRuns(runListParams, {
    query: {
      enabled: !!runListParams,
      keepPreviousData: true,
    },
  });
  const runListPayload = runListQuery.data?.data;

  // Normalize run list for the dropdown
  const availableRuns = React.useMemo(() => {
    if (!runListPayload) return [];
    const rawItems = Array.isArray(runListPayload.items) ? runListPayload.items : [];
    const candidates = [...rawItems];
    if (runListPayload.latest) {
      const latestKey =
        runListPayload.latest.run_id ??
        runListPayload.latest.as_of ??
        runListPayload.latest.trade_date;
      const already = candidates.some((item) => {
        const key = item.run_id ?? item.as_of ?? item.trade_date;
        return key && latestKey && key === latestKey;
      });
      if (!already) {
        candidates.unshift(runListPayload.latest);
      }
    }
    return candidates.map((item, index) => {
      const key = item.run_id ?? item.as_of ?? item.trade_date ?? `run-${index}`;
      const label =
        item.label ??
        (pendingMode === MODE_INTRADAY
          ? item.run_id ?? item.trade_date ?? `Run ${index + 1}`
          : item.as_of ?? `Run ${index + 1}`);
      const secondary = pendingMode === MODE_INTRADAY ? item.trade_date : item.as_of;
      return { key, label, secondary, summary: item };
    });
  }, [runListPayload, pendingMode]);

  // Keep pendingRun in sync with the latest list (but don't override programmatic initial seed)
  React.useEffect(() => {
    if (!runListPayload) {
      setPendingRun(null);
      return;
    }
    const items = runListPayload.items ?? [];
    if (items.length === 0) {
      setPendingRun(null);
      return;
    }
    const fallback = runListPayload.latest ?? items[0];
    if (!pendingRun) {
      setPendingRun(fallback);
      return;
    }
    const pendingKey = pendingRun.run_id ?? pendingRun.as_of ?? pendingRun.trade_date;
    const stillExists = items.some((item) => {
      const key = item.run_id ?? item.as_of ?? item.trade_date;
      return key === pendingKey;
    });
    if (!stillExists) {
      setPendingRun(fallback);
    }
  }, [runListPayload, pendingRun]);

  const pendingRunKey = pendingRun
    ? pendingRun.run_id ?? pendingRun.as_of ?? pendingRun.trade_date ?? ''
    : '';

  // APPLY: Intraday uses run_id; EOD uses as_of ONLY (never run_id)
  const applySelection = React.useCallback((mode: Mode, run: ScreenerRunSummary, date: string | undefined) => {
    setAppliedMode(mode);
    if (mode === MODE_INTRADAY) {
      setAppliedRunId(run.run_id ?? undefined);
      setAppliedAsOf(undefined);
    } else {
      // EOD: never send run_id; only as_of
      setAppliedRunId(undefined);
      setAppliedAsOf(run.as_of ?? date ?? undefined);
    }
  }, []);

  const handleApply = React.useCallback(() => {
    if (!pendingRun) return;
    applySelection(pendingMode, pendingRun, pendingDate);
  }, [applySelection, pendingMode, pendingRun, pendingDate]);

  // Auto-apply once when we have a pending run (first load or after seeding)
  React.useEffect(() => {
    if (!hasAppliedInitial && pendingRun) {
      applySelection(pendingMode, pendingRun, pendingDate);
      setHasAppliedInitial(true);
    }
  }, [hasAppliedInitial, pendingRun, pendingMode, pendingDate, applySelection]);

  const handleModeChange = React.useCallback((_: React.SyntheticEvent, value: Mode | null) => {
    if (!value) return;
    setPendingMode(value);
    setHasAppliedInitial(false); // allow re-apply on explicit mode change
  }, []);

  const handleDateInputChange = React.useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    const value = event.target.value;
    setPendingDate(value || undefined);
    setPendingRun(null);
    setHasAppliedInitial(false); // allow re-apply when date changes
  }, []);

  const handleRunChange = React.useCallback((event: SelectChangeEvent<string>) => {
    const value = event.target.value;
    if (!value) {
      setPendingRun(null);
      return;
    }
    const match = availableRuns.find((item) => item.key === value);
    setPendingRun(match?.summary ?? null);
    setHasAppliedInitial(false); // allow re-apply when run changes
  }, [availableRuns]);

  const handleOpenExportMenu = React.useCallback((event: React.MouseEvent<HTMLElement>) => {
    setExportAnchorEl(event.currentTarget);
  }, []);

  const handleCloseExportMenu = React.useCallback(() => {
    setExportAnchorEl(null);
  }, []);

  const handleExport = React.useCallback(
    async (fmt: 'csv' | 'json') => {
      const isIntraday = appliedMode === MODE_INTRADAY;
      const hasSelection = isIntraday ? !!appliedRunId : !!appliedAsOf;
      if (!hasSelection) {
        window.alert('Select a snapshot before exporting.');
        return;
      }

      const params = new URLSearchParams();
      if (isIntraday) {
        if (!appliedRunId) {
          window.alert('Select an intraday run to export.');
          return;
        }
        params.append('run_id', appliedRunId);
      } else {
        // EOD: export strictly by as_of
        if (appliedAsOf) {
          params.append('as_of', appliedAsOf);
        } else {
          window.alert('Select an EOD snapshot to export.');
          return;
        }
      }
      params.append('format', fmt);

      setIsExporting(true);
      try {
        const response = await fetch(`/api/v1/screener/export?${params.toString()}`);
        if (!response.ok) {
          const detail = await response.json().catch(() => null);
          console.error('Export failed', response.status, detail);
          window.alert('Export failed. Please try again.');
          return;
        }
        const blob = await response.blob();
        let filename = `screener_${appliedMode}_${appliedRunId || appliedAsOf || 'latest'}.${fmt}`;
        const disposition = response.headers.get('content-disposition');
        if (disposition) {
          const match = disposition.match(/filename="?([^";]+)"?/i);
          if (match?.[1]) {
            filename = match[1];
          }
        }
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
      } catch (error) {
        console.error('Export exception', error);
        window.alert('Export failed. Please try again.');
      } finally {
        setIsExporting(false);
        setExportAnchorEl(null);
      }
    },
    [appliedMode, appliedRunId, appliedAsOf],
  );

  const isRunDatesLoading = runDatesQuery.isLoading;
  const isRunListLoading = runListQuery.isFetching;
  const hasAppliedSelection = appliedMode === MODE_INTRADAY
    ? !!appliedRunId
    : !!appliedAsOf;
  const exportMenuOpen = Boolean(exportAnchorEl);

  // ---- NEW: Auto-seed mode/date/run from /api/v1/screener/latest (EOD > Intraday) ----
  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const resp = await fetch('/api/v1/screener/latest');
        if (!resp.ok) return;
        const latest: ScreenerRunSummary = await resp.json();
        if (cancelled || !latest) return;

        const nextMode: Mode = latest.mode === 'eod' ? MODE_EOD : MODE_INTRADAY;
        const nextDate =
          nextMode === MODE_INTRADAY
            ? (latest.trade_date ?? undefined)
            : (latest.as_of ?? undefined);

        // Prevent the mode-change reset from wiping our seeded date/run
        suppressModeResetRef.current = true;
        setPendingMode(nextMode);
        setPendingDate(nextDate);
        setPendingRun(latest);

        // Allow the "auto-apply" effect to run with the seeded selection
        setHasAppliedInitial(false);
      } catch (e) {
        // Non-fatal; UI will fall back to existing run-dates logic
        // eslint-disable-next-line no-console
        console.error('latest snapshot fetch failed', e);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  return (
    <Paper sx={{ p: 2, width: '100%', display: 'flex', flexDirection: 'column', gap: 1 }}>
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        alignItems={{ xs: 'flex-start', sm: 'center' }}
        justifyContent="space-between"
        spacing={1}
        sx={{ mb: 1 }}
      >
        <Stack spacing={0.25}>
          <Typography variant="subtitle2">Full Screener</Typography>
          <Typography variant="caption" color="text.secondary">
            Filter, sort, and explore the full universe
          </Typography>
        </Stack>
        <Stack
          direction={{ xs: 'column', lg: 'row' }}
          spacing={1}
          alignItems={{ xs: 'stretch', lg: 'center' }}
          flexWrap="wrap"
          sx={{ width: '100%' }}
        >
          <Stack
            component="form"
            direction={{ xs: 'column', sm: 'row' }}
            spacing={1}
            alignItems={{ xs: 'stretch', sm: 'center' }}
            onSubmit={handleTickerSubmit}
          >
            <TextField
              size="small"
              label="Ticker"
              placeholder="e.g. SUMEETINDS.NS"
              value={tickerInput}
              onChange={(event) => setTickerInput(event.target.value)}
              autoComplete="off"
              sx={{ minWidth: { xs: '100%', sm: 220 } }}
            />
            <Button type="submit" variant="contained" size="small">
              Search
            </Button>
            {(tickerInput || symbolFilter) ? (
              <Button type="button" variant="outlined" size="small" onClick={handleClear}>
                Clear
              </Button>
            ) : null}
          </Stack>
          <ToggleButtonGroup
            exclusive
            size="small"
            value={pendingMode}
            onChange={handleModeChange}
          >
            <ToggleButton value={MODE_INTRADAY}>Intraday</ToggleButton>
            <ToggleButton value={MODE_EOD}>EOD</ToggleButton>
          </ToggleButtonGroup>
          <TextField
            type="date"
            size="small"
            label={pendingMode === MODE_INTRADAY ? 'Trade Date' : 'EOD Date'}
            value={pendingDate ?? ''}
            onChange={handleDateInputChange}
            InputLabelProps={{ shrink: true }}
            sx={{ minWidth: { xs: '100%', sm: 200 } }}
            helperText={
              availableDates.length === 0 && !pendingDate
                ? isRunDatesLoading
                  ? 'Loading available dates…'
                  : 'No dates available'
                : undefined
            }
          />
          <FormControl
            size="small"
            sx={{ minWidth: { xs: '100%', sm: 220 } }}
          >
            <InputLabel id="screener-run-label">
              {pendingMode === MODE_INTRADAY ? 'Run' : 'Snapshot'}
            </InputLabel>
            <Select
              labelId="screener-run-label"
              label={pendingMode === MODE_INTRADAY ? 'Run' : 'Snapshot'}
              value={pendingRunKey}
              onChange={handleRunChange}
              displayEmpty
              renderValue={(value) => {
                if (!value) {
                  return <Typography variant="body2" color="text.secondary">Select run</Typography>;
                }
                const selected = availableRuns.find((item) => item.key === value);
                return selected?.label ?? value;
              }}
            >
              {isRunListLoading ? (
                <MenuItem value="" disabled>
                  <Stack direction="row" spacing={1} alignItems="center">
                    <CircularProgress size={16} />
                    <Typography variant="body2">Loading</Typography>
                  </Stack>
                </MenuItem>
              ) : availableRuns.length === 0 ? (
                <MenuItem value="" disabled>
                  No runs found
                </MenuItem>
              ) : (
                availableRuns.map((item) => (
                  <MenuItem key={item.key} value={item.key}>
                    <Stack spacing={0.25}>
                      <Typography variant="body2" fontWeight={500}>
                        {item.label}
                      </Typography>
                      {item.secondary ? (
                        <Typography variant="caption" color="text.secondary">
                          {item.secondary}
                        </Typography>
                      ) : null}
                    </Stack>
                  </MenuItem>
                ))
              )}
            </Select>
          </FormControl>
          <Button
            variant="contained"
            size="small"
            onClick={handleApply}
            disabled={!pendingRun}
          >
            Submit
          </Button>
          <Button
            variant="outlined"
            size="small"
            startIcon={<DownloadIcon fontSize="small" />}
            onClick={handleOpenExportMenu}
            disabled={!hasAppliedSelection || isExporting}
          >
            Export
          </Button>
          <Menu
            anchorEl={exportAnchorEl}
            open={Boolean(exportAnchorEl)}
            onClose={handleCloseExportMenu}
            anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
          >
            <MenuItem onClick={() => handleExport('csv')} disabled={isExporting}>
              CSV
            </MenuItem>
            <MenuItem onClick={() => handleExport('json')} disabled={isExporting}>
              JSON
            </MenuItem>
          </Menu>
        </Stack>
      </Stack>
      <Divider sx={{ mb: 1 }} />
      <Box sx={{ width: '100%' }}>
        <MomentumTable
          key={`${appliedMode}-${appliedRunId ?? 'none'}-${appliedAsOf ?? 'none'}`}
          refetchIntervalMs={refetchIntervalMs}
          symbolFilter={symbolFilter}
          runId={appliedRunId}
          asOf={appliedAsOf}
        />
      </Box>
    </Paper>
  );
}
