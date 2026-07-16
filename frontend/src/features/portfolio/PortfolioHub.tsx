import React from 'react';
import { Box, Tab, Tabs } from '@mui/material';
import PortfolioDataImport from './PortfolioDataImport';
import PortfolioSummaryHeader from './PortfolioSummaryHeader';
import WealthGoalWorkspace from './WealthGoalWorkspace';
import PortfolioOverview from './PortfolioOverview';
import PortfolioAnnualReview from './PortfolioAnnualReview';
import PortfolioPropertiesRent from './PortfolioPropertiesRent';

const TAB_LABELS = ['Overview', 'Annual Review', 'Investments', 'Properties & Rent', 'Goals', 'Data Import'] as const;

export const portfolioPanelForTab = (tab: number, investments: React.ReactNode, setTab: (tab: number) => void): React.ReactNode => {
  if (tab === 0) return <PortfolioOverview />;
  if (tab === 1) return <PortfolioAnnualReview />;
  if (tab === 2) return investments;
  if (tab === 3) return <PortfolioPropertiesRent />;
  if (tab === 4) return <WealthGoalWorkspace onOpenDataImport={() => setTab(5)} />;
  if (tab === 5) return <PortfolioDataImport />;
  return null;
};

const PortfolioHub: React.FC<{ investments: React.ReactNode }> = ({ investments }) => {
  const [tab, setTab] = React.useState(2);
  return <Box sx={{ px: { xs: 1, md: 2 }, pb: 2 }}>
    <PortfolioSummaryHeader />
    <Tabs value={tab} onChange={(_, value: number) => setTab(value)} variant="scrollable" scrollButtons="auto" aria-label="Portfolio sections" sx={{ mt: 1.5, mb: 2, borderBottom: '1px solid', borderColor: 'divider' }}>
      {TAB_LABELS.map((label, index) => <Tab key={label} id={`portfolio-tab-${index}`} aria-controls={`portfolio-panel-${index}`} label={label} />)}
    </Tabs>
    <Box role="tabpanel" id={`portfolio-panel-${tab}`} aria-labelledby={`portfolio-tab-${tab}`}>
      {portfolioPanelForTab(tab, investments, setTab)}
    </Box>
  </Box>;
};

export default PortfolioHub;
