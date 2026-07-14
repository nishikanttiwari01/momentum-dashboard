import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { PortfolioMetricTile, PortfolioSectionHeader, assetIconFor } from './PortfolioVisuals';

describe('PortfolioVisuals', () => {
  it('renders icon-led section headings and financial metric tiles', () => {
    const heading = renderToStaticMarkup(<PortfolioSectionHeader icon={assetIconFor('Mutual funds')} title="Current assets" detail="Workbook values" />);
    const metric = renderToStaticMarkup(<PortfolioMetricTile icon={assetIconFor('Stocks')} label="Market value" value="₹8.31 Cr" tone="positive" />);
    expect(heading).toContain('Current assets');
    expect(heading).toContain('Workbook values');
    expect(heading).toContain('data-portfolio-icon="mutual-funds"');
    expect(metric).toContain('Market value');
    expect(metric).toContain('₹8.31 Cr');
    expect(metric).toContain('data-tone="positive"');
  });
});
