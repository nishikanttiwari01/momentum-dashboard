import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it } from 'vitest';
import PortfolioHub from './PortfolioHub';

describe('PortfolioHub', () => {
  it('keeps investments as the working default and exposes all planned tabs', () => {
    const html = renderToStaticMarkup(<QueryClientProvider client={new QueryClient()}><PortfolioHub investments={<div>Mutual funds and QQQ</div>} /></QueryClientProvider>);
    for (const label of ['Overview', 'Annual Review', 'Investments', 'Properties &amp; Rent', 'Goals', 'Data Import']) expect(html).toContain(label);
    expect(html).toContain('Mutual funds and QQQ');
  });
});
