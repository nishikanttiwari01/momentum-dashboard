import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import PortfolioWorkbookPreview from './PortfolioWorkbookPreview';

describe('PortfolioWorkbookPreview', () => {
  it('is explicitly preview-only and lists every approved current-portfolio sheet', () => {
    const html = renderToStaticMarkup(<PortfolioWorkbookPreview />);
    expect(html).toContain('accept=".xlsx"');
    for (const sheet of ['BALANCE SHEET', 'CURRENT ASSET', 'FUNDS', 'Funds XIRR', 'Final XIRR', 'EQUITY', 'FIXED ASSET']) {
      expect(html).toContain(sheet);
    }
    expect(html).toContain('UI preview only');
    expect(html).toContain('not uploaded or saved');
    expect(html).toContain('Private identity and access fields are excluded');
  });
});
