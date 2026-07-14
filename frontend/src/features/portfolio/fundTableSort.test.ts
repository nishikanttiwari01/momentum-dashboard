import { describe, expect, it } from 'vitest';
import { sortFunds, type FundSortRecord } from './fundTableSort';

const fund = (
  id: string,
  name: string,
  overrides: Partial<FundSortRecord> = {},
): FundSortRecord => ({
  id,
  name,
  category: 'Mid cap',
  performance: {},
  totals: null,
  combined_holding: null,
  ...overrides,
});

describe('sortFunds', () => {
  it('preserves API order until a sort key is selected', () => {
    const funds = [fund('z', 'Zulu'), fund('a', 'alpha')];
    expect(sortFunds(funds, null, 'asc')).toEqual(funds);
    expect(sortFunds(funds, null, 'asc')).not.toBe(funds);
  });

  it('sorts fund names case-insensitively', () => {
    const funds = [fund('z', 'Zulu'), fund('b', 'Beta'), fund('a', 'alpha')];
    expect(sortFunds(funds, 'fund', 'asc').map((item) => item.name)).toEqual(['alpha', 'Beta', 'Zulu']);
  });

  it('sorts raw invested values in both directions', () => {
    const funds = [
      fund('low', 'Low', { totals: { invested: 100 } }),
      fund('high', 'High', { totals: { invested: 900 } }),
      fund('mid', 'Mid', { totals: { invested: 400 } }),
    ];
    expect(sortFunds(funds, 'invested', 'asc').map((item) => item.id)).toEqual(['low', 'mid', 'high']);
    expect(sortFunds(funds, 'invested', 'desc').map((item) => item.id)).toEqual(['high', 'mid', 'low']);
  });

  it('keeps missing values last in ascending and descending order', () => {
    const funds = [
      fund('missing', 'Missing'),
      fund('high', 'High', { totals: { invested: 900, xirr_pct: 18 } }),
      fund('low', 'Low', { totals: { invested: 100, xirr_pct: 8 } }),
    ];
    expect(sortFunds(funds, 'xirr', 'asc').map((item) => item.id)).toEqual(['low', 'high', 'missing']);
    expect(sortFunds(funds, 'xirr', 'desc').map((item) => item.id)).toEqual(['high', 'low', 'missing']);
  });

  it('preserves API order for equal values', () => {
    const funds = [fund('first', 'One'), fund('second', 'Two'), fund('third', 'Three')];
    expect(sortFunds(funds, 'category', 'asc').map((item) => item.id)).toEqual(['first', 'second', 'third']);
  });
});
