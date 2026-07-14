import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import PortfolioAllocation from './PortfolioAllocation';

describe('PortfolioAllocation', () => {
  it('renders an accessible category donut with percentages and amounts', () => {
    const html = renderToStaticMarkup(
      <PortfolioAllocation
        allocation={[
          { category: 'SMALL_CAP', value: 239333428, weight_pct: 75.8 },
          { category: 'MID_CAP', value: 3896619, weight_pct: 12.3 },
        ]}
      />,
    );

    expect(html).toContain('aria-label="Allocation by category"');
    expect(html).toContain('data-testid="portfolio-allocation-compact"');
    expect(html).toContain('width="150"');
    expect(html).toContain('Small cap');
    expect(html).toContain('75.8%');
    expect(html).toContain('₹23,93,33,428');
    expect(html).toContain('Mid cap');
  });
});
