import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { PortfolioSummaryHeaderView } from './PortfolioSummaryHeader';

describe('PortfolioSummaryHeaderView', () => {
  it('renders consolidated INR value and FX provenance', () => {
    const html = renderToStaticMarkup(<PortfolioSummaryHeaderView summary={{
      snapshot_id: 's1', as_of: '2026-07-14', net_worth_market_value_inr: 83100000,
      invested_capital_inr: 58200000, investment_xirr_pct: null, market_exposure: [],
      fx: { pair: 'USD/INR', rate: 86.25, effective_on: '2026-07-14', fetched_at: '2026-07-14T10:00:00', source: 'frankfurter', is_fallback: false },
      data_health: 'fresh',
    }} />);
    expect(html).toContain('Net worth market value');
    expect(html).toContain('₹8.31 Cr');
    expect(html).toContain('Combined household value · property included');
    expect(html).not.toMatch(/â‚¹|Â·|â€”|Ã/);
    expect(html).toContain('USD/INR 86.25');
  });
});
