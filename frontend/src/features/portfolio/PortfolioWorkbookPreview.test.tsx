import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import PortfolioWorkbookPreview from './PortfolioWorkbookPreview';

describe('PortfolioWorkbookPreview', () => {
  it('forwards to the real workbook import workflow', () => {
    const html = renderToStaticMarkup(<QueryClientProvider client={new QueryClient()}><PortfolioWorkbookPreview /></QueryClientProvider>);
    expect(html).toContain('accept=".xlsx"');
    expect(html).toContain('Validate before importing');
    expect(html).not.toContain('UI preview only');
  });
});
