import React from 'react';
import { Alert, Box, Tab, Tabs } from '@mui/material';
import PortfolioDataImport from './PortfolioDataImport';
import PortfolioSummaryHeader from './PortfolioSummaryHeader';

const TAB_LABELS = ['Overview', 'Annual Review', 'Investments', 'Properties & Rent', 'Goals', 'Data Import'] as const;

const PortfolioHub: React.FC<{ investments: React.ReactNode }> = ({ investments }) => {
  const [tab, setTab] = React.useState(2);
  return <Box sx={{ px: { xs: 1, md: 2 }, pb: 2 }}>
    <PortfolioSummaryHeader />
    <Tabs value={tab} onChange={(_, value: number) => setTab(value)} variant="scrollable" scrollButtons="auto" aria-label="Portfolio sections" sx={{ mt: 1.5, mb: 2, borderBottom: '1px solid', borderColor: 'divider' }}>
      {TAB_LABELS.map(label => <Tab key={label} label={label} />)}
    </Tabs>
    {tab === 2 ? investments : null}
    {tab === 5 ? <PortfolioDataImport /> : null}
    {tab !== 2 && tab !== 5 ? <Alert severity="info">{TAB_LABELS[tab]} will be activated in the next portfolio delivery phase. No placeholder values are shown.</Alert> : null}
  </Box>;
};

export default PortfolioHub;
