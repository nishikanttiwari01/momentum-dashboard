import React from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Paper,
  Stack,
  Typography,
} from '@mui/material';
import UploadFileRoundedIcon from '@mui/icons-material/UploadFileRounded';
import { useQueryClient } from '@tanstack/react-query';
import { commitWorkbook, previewWorkbook } from './wealthApi';
import type { ImportPreview } from './wealthTypes';

type Status = 'idle' | 'previewing' | 'ready' | 'committing' | 'success' | 'error';

const PortfolioDataImport: React.FC = () => {
  const queryClient = useQueryClient();
  const [status, setStatus] = React.useState<Status>('idle');
  const [preview, setPreview] = React.useState<ImportPreview | null>(null);
  const [filename, setFilename] = React.useState<string | null>(null);
  const [message, setMessage] = React.useState<string | null>(null);

  const selectWorkbook = async (file: File | undefined) => {
    if (!file) return;
    setFilename(file.name);
    setPreview(null);
    setMessage(null);
    setStatus('previewing');
    try {
      const next = await previewWorkbook(file);
      setPreview(next);
      setStatus('ready');
    } catch {
      setStatus('error');
      setMessage('The workbook could not be validated. Check the file and try again.');
    }
  };

  const importSnapshot = async () => {
    if (!preview || preview.blocking_error_count > 0) return;
    setStatus('committing');
    try {
      const result = await commitWorkbook(preview.preview_token);
      setStatus('success');
      setMessage(result.created ? 'Snapshot imported successfully.' : 'This workbook was already imported; the existing snapshot is unchanged.');
      await queryClient.invalidateQueries({ queryKey: ['wealth-summary'] });
    } catch {
      setStatus('error');
      setMessage('The snapshot was not imported. Existing portfolio data is unchanged.');
    }
  };

  const busy = status === 'previewing' || status === 'committing';
  return (
    <Paper variant="outlined" sx={{ overflow: 'hidden' }}>
      <Box sx={{ px: 2.5, py: 1.5, borderBottom: '1px solid', borderColor: 'divider' }}>
        <Typography variant="overline" fontWeight={800} letterSpacing="0.12em">Refresh from Excel</Typography>
        <Typography variant="body2" color="text.secondary">Validate before importing. A successful import creates an immutable dated snapshot.</Typography>
      </Box>
      <Box sx={{ p: 2.5, display: 'grid', gridTemplateColumns: { xs: '1fr', md: '320px minmax(0, 1fr)' }, gap: 2 }}>
        <Box sx={{ border: '1px dashed', borderColor: 'primary.light', borderRadius: 2, bgcolor: 'action.hover', p: 3, textAlign: 'center' }}>
          <UploadFileRoundedIcon color="primary" sx={{ fontSize: 36 }} />
          <Typography fontWeight={800} sx={{ mt: 1 }}>Update portfolio snapshot</Typography>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>Choose the latest investment workbook. Nothing is saved until you confirm the validated preview.</Typography>
          <Button component="label" variant="contained" size="small" disabled={busy} sx={{ mt: 2 }}>
            Choose .xlsx workbook
            <input aria-label="Choose .xlsx workbook" hidden type="file" accept=".xlsx" onChange={(event) => void selectWorkbook(event.target.files?.[0])} />
          </Button>
          {filename ? <Typography variant="caption" display="block" sx={{ mt: 1 }}>{filename}</Typography> : null}
        </Box>
        <Box sx={{ minWidth: 0 }}>
          {status === 'idle' ? <Alert severity="info">Choose a workbook to see recognized sheets, record counts and validation issues.</Alert> : null}
          {status === 'previewing' ? <Stack alignItems="center" spacing={1} sx={{ py: 4 }}><CircularProgress size={28} /><Typography variant="body2">Validating workbook…</Typography></Stack> : null}
          {preview ? <Stack spacing={1.5}>
            <Stack direction="row" justifyContent="space-between" alignItems="center"><Typography fontWeight={800}>Import preview</Typography><Chip size="small" color={preview.blocking_error_count ? 'error' : 'success'} label={preview.blocking_error_count ? `${preview.blocking_error_count} blocking errors` : 'Ready to import'} /></Stack>
            <Stack direction="row" flexWrap="wrap" useFlexGap gap={1}>{Object.entries(preview.counts).map(([name, count]) => <Chip key={name} size="small" label={`${count} ${name}`} />)}</Stack>
            <Box><Typography variant="caption" color="text.secondary">Recognized sheets</Typography><Stack direction="row" flexWrap="wrap" useFlexGap gap={0.75} sx={{ mt: 0.5 }}>{preview.recognized_sheets.map((sheet) => <Chip key={sheet} size="small" variant="outlined" color="success" label={sheet} />)}</Stack></Box>
            {preview.ignored_sheets.length ? <Box><Typography variant="caption" color="text.secondary">Ignored by design</Typography><Stack direction="row" flexWrap="wrap" useFlexGap gap={0.75} sx={{ mt: 0.5 }}>{preview.ignored_sheets.map((sheet) => <Chip key={sheet} size="small" variant="outlined" label={sheet} />)}</Stack></Box> : null}
            {preview.issues.map((issue, index) => <Alert key={`${issue.code}-${index}`} severity={issue.severity}>{issue.message}{issue.sheet ? ` (${issue.sheet}${issue.row ? ` row ${issue.row}` : ''})` : ''}</Alert>)}
            <Button variant="contained" onClick={() => void importSnapshot()} disabled={busy || preview.blocking_error_count > 0}>{status === 'committing' ? 'Importing…' : 'Import snapshot'}</Button>
          </Stack> : null}
          {message ? <Alert severity={status === 'success' ? 'success' : 'error'} sx={{ mt: 1 }}>{message}</Alert> : null}
        </Box>
      </Box>
      <Typography variant="caption" color="warning.dark" sx={{ display: 'block', bgcolor: 'warning.50', px: 2.5, py: 1 }}>
        Ignored sheets are never read or stored. A failed or cancelled import leaves the current portfolio unchanged.
      </Typography>
    </Paper>
  );
};

export default PortfolioDataImport;
