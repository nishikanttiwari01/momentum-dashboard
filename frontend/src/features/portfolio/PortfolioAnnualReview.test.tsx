import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { PortfolioAnnualReviewView } from './PortfolioAnnualReview';
import type { AnnualReviewField, AnnualReviewResponse } from './wealthTypes';

const field = (value: number | null, source: AnnualReviewField['source'] = 'calculated'): AnnualReviewField => ({ value, calculated_value: value, source: value == null ? 'missing' : source, explanation: 'Test source' });
const review: AnnualReviewResponse = {
  year: 2025, opening_snapshot_date: '2024-12-31', closing_snapshot_date: '2025-12-31',
  reporting_label: 'FY-2025', selection_method: 'workbook_formula_lineage',
  source_dates: { financial_market_value: '2025-12-31', property_market_value: '2025-09-01' },
  opening_net_worth_inr: field(80_000_000, 'imported'), contributions_inr: field(6_000_000),
  investment_gain_inr: field(5_000_000), property_gain_inr: field(2_000_000),
  rent_received_inr: field(600_000, 'manual'), withdrawals_inr: field(100_000),
  closing_net_worth_inr: field(93_500_000, 'imported'), investment_xirr_pct: field(12.5),
  reconciliation: { status: 'reconciled', expected_closing_inr: 93_500_000, difference_inr: 0 }, notes: null,
};

describe('PortfolioAnnualReviewView', () => {
  it('shows effective values, provenance, and reconciliation', () => {
    const html = renderToStaticMarkup(<PortfolioAnnualReviewView reviews={[review]} selectedYear={2025} onSelectYear={vi.fn()} onEdit={vi.fn()} />);
    expect(html).toContain('FY-2025 source period');
    expect(html).toContain('Financial market 31 Dec 2025');
    expect(html).toContain('Annual wealth review');
    expect(html).toContain('Manual override');
    expect(html).toContain('Reconciled');
    expect(html).toContain('12.5%');
    expect(html).not.toContain('sample data');
  });
});
