import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import PortfolioWorkbookSnapshot, { PortfolioWealthGrowth } from './PortfolioWorkbookSnapshot';

describe('PortfolioWorkbookSnapshot', () => {
  it('renders wealth growth, asset groups and the year-wise balance sheet', () => {
    const html = renderToStaticMarkup(<PortfolioWorkbookSnapshot />);
    expect(html).toContain('Wealth growth over years');
    expect(html).toContain('Stocks &amp; current assets');
    expect(html).toContain('Fixed assets');
    expect(html).toContain('Balance sheet — year wise');
    expect(html).toContain('FY-24');
    expect(html).toContain('FY-25');
    expect(html).toContain('FY-26');
    expect(html).toContain('₹8.31 Cr');
    expect(html).toContain('Gera office');
    expect(html).toContain('Brigade land');
  });

  it('exposes wealth growth as a standalone dashboard panel', () => {
    const html = renderToStaticMarkup(<PortfolioWealthGrowth />);
    expect(html).toContain('data-testid="portfolio-wealth-growth"');
    expect(html).toContain('data-chart-type="wealth-area"');
    expect(html).toContain('Wealth growth over years');
    expect(html).toContain('₹5.82 Cr');
    expect(html).toContain('₹8.25 Cr');
    expect(html).toContain('₹8.31 Cr');
    expect(html).not.toContain('Stocks &amp; current assets');
  });

  it('uses meaningful icons for asset rows', () => {
    const html = renderToStaticMarkup(<PortfolioWorkbookSnapshot />);
    expect(html).toContain('data-portfolio-icon="mutual-funds"');
    expect(html).toContain('data-portfolio-icon="stocks"');
    expect(html).toContain('data-portfolio-icon="property"');
    expect(html).toContain('data-portfolio-icon="office"');
  });
});
