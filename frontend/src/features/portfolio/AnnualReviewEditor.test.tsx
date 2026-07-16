import { describe, expect, it } from 'vitest';
import { buildAnnualReviewOverridePayload } from './AnnualReviewEditor';

describe('AnnualReviewEditor', () => {
  it('sends only changed fields and supports restoring a calculated field with null', () => {
    expect(buildAnnualReviewOverridePayload(
      { rent_received_inr: '600000', investment_xirr_pct: '12.5', notes: 'Checked' },
      new Set(['rent_received_inr', 'notes']),
    )).toEqual({ rent_received_inr: 600000, notes: 'Checked' });

    expect(buildAnnualReviewOverridePayload(
      { rent_received_inr: '', investment_xirr_pct: '', notes: '' },
      new Set(['rent_received_inr']),
    )).toEqual({ rent_received_inr: null });
  });
});
