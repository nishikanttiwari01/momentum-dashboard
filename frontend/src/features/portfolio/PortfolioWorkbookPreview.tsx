import React from 'react';
import { Box, Button, Chip, Paper, Stack, Typography } from '@mui/material';

const APPROVED_SHEETS = ['BALANCE SHEET', 'CURRENT ASSET', 'FUNDS', 'Funds XIRR', 'Final XIRR', 'EQUITY', 'FIXED ASSET'];

const PortfolioWorkbookPreview: React.FC = () => {
  const [filename, setFilename] = React.useState<string | null>(null);

  return (
    <Paper variant="outlined" sx={{ overflow: 'hidden' }}>
      <Box sx={{ px: 2, py: 1.25, borderBottom: '1px solid', borderColor: 'divider', display: 'flex', alignItems: 'center', gap: 1 }}>
        <Box sx={{ width: 8, height: 8, borderRadius: 0.5, bgcolor: '#7a5af8' }} />
        <Typography variant="overline" fontWeight={700} letterSpacing="0.12em">Refresh from Excel</Typography>
        <Typography variant="caption" color="text.secondary">UI preview only</Typography>
      </Box>
      <Box sx={{ p: 2, display: 'grid', gridTemplateColumns: { xs: '1fr', md: '300px 1fr' }, gap: 2 }}>
        <Box sx={{ border: '1px dashed', borderColor: 'primary.light', borderRadius: 1, bgcolor: 'action.hover', p: 2.5, textAlign: 'center' }}>
          <Typography fontWeight={700}>Update portfolio snapshot</Typography>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>Select an updated investment workbook to review the future import flow.</Typography>
          <Button component="label" variant="contained" size="small" sx={{ mt: 1.5 }}>
            Choose .xlsx workbook
            <input hidden type="file" accept=".xlsx" onChange={(event) => setFilename(event.target.files?.[0]?.name ?? null)} />
          </Button>
        </Box>
        <Box sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 1, p: 2, minHeight: 150 }}>
          <Stack direction="row" justifyContent="space-between" gap={2}>
            <Typography fontWeight={700}>{filename ? 'Ready to preview' : 'Import preview'}</Typography>
            {filename ? <Typography variant="caption" color="success.main">✓ sample totals reconcile</Typography> : null}
          </Stack>
          <Typography variant="caption" color="text.secondary">{filename ? `${filename} · recognized current-portfolio sheets` : 'Choose a workbook to preview recognized sheets. The file is not uploaded or saved.'}</Typography>
          <Stack direction="row" flexWrap="wrap" useFlexGap gap={0.75} sx={{ mt: 1.25 }}>
            {APPROVED_SHEETS.map((sheet) => <Chip key={sheet} size="small" label={sheet} color={filename ? 'success' : 'default'} variant="outlined" />)}
          </Stack>
          {filename ? (
            <Stack direction="row" flexWrap="wrap" useFlexGap gap={2.5} sx={{ mt: 1.5 }}>
              <Typography variant="caption"><b>4</b> holdings updated</Typography>
              <Typography variant="caption"><b>2</b> transactions added</Typography>
              <Typography variant="caption"><b>0</b> blocking errors</Typography>
            </Stack>
          ) : null}
        </Box>
      </Box>
      <Typography variant="caption" color="warning.dark" sx={{ display: 'block', bgcolor: 'warning.50', px: 2, py: 1 }}>
        Private identity and access fields are excluded. Existing app data and transaction history remain unchanged in this UI phase.
      </Typography>
    </Paper>
  );
};

export default PortfolioWorkbookPreview;
