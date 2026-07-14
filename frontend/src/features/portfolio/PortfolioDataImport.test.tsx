import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import PortfolioDataImport from './PortfolioDataImport';

describe('PortfolioDataImport', () => {
  it('renders the real workbook upload entry point and privacy boundary', () => {
    const html = renderToStaticMarkup(<QueryClientProvider client={new QueryClient()}><PortfolioDataImport /></QueryClientProvider>);
    expect(html).toContain('Choose .xlsx workbook');
    expect(html).toContain('accept=".xlsx"');
    expect(html).toContain('Validate before importing');
    expect(html).toContain('Ignored sheets are never read or stored');
    expect(html).not.toContain('UI preview only');
  });
});
