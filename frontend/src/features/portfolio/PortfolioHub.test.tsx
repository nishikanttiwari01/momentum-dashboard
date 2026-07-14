import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it } from 'vitest';
import { Alert } from '@mui/material';
import PortfolioHub, { portfolioPanelForTab } from './PortfolioHub';
import PortfolioDataImport from './PortfolioDataImport';
import WealthGoalWorkspace from './WealthGoalWorkspace';

describe('PortfolioHub', () => {
  it('keeps investments as the working default and exposes all planned tabs', () => {
    const html = renderToStaticMarkup(<QueryClientProvider client={new QueryClient()}><PortfolioHub investments={<div>Mutual funds and QQQ</div>} /></QueryClientProvider>);
    for (const label of ['Overview', 'Annual Review', 'Investments', 'Properties &amp; Rent', 'Goals', 'Data Import']) expect(html).toContain(label);
    expect(html).toContain('Mutual funds and QQQ');
  });

  it('selects the goals workspace and maps its data-import action to tab 5', () => {
    let selectedTab = 4;
    const panel = portfolioPanelForTab(selectedTab, <div>Investments</div>, value => { selectedTab = value; });

    expect(React.isValidElement(panel)).toBe(true);
    expect((panel as React.ReactElement).type).toBe(WealthGoalWorkspace);
    (panel as React.ReactElement<{ onOpenDataImport: () => void }>).props.onOpenDataImport();
    expect(selectedTab).toBe(5);
    expect((portfolioPanelForTab(selectedTab, <div>Investments</div>, () => undefined) as React.ReactElement).type).toBe(PortfolioDataImport);
  });

  it.each([0, 1, 3])('keeps future portfolio tab %i as an informational alert', tab => {
    const panel = portfolioPanelForTab(tab, <div>Investments</div>, () => undefined);

    expect((panel as React.ReactElement).type).toBe(Alert);
  });
});
