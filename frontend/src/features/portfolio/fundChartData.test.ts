import { describe, expect, it } from 'vitest';
import { buildFundChartSeries } from './fundChartData';

describe('buildFundChartSeries', () => {
  it('keeps every multi-year NAV point on a unique numeric time axis', () => {
    const result = buildFundChartSeries([
      { date: '2021-07-09', nav: 50 },
      { date: '2021-07-12', nav: 51 },
      { date: '2021-07-13', nav: 52 },
    ], []);
    expect(result.prices.map(point => point.time)).toEqual([
      Date.parse('2021-07-09T00:00:00Z'),
      Date.parse('2021-07-12T00:00:00Z'),
      Date.parse('2021-07-13T00:00:00Z'),
    ]);
    expect(new Set(result.prices.map(point => point.time)).size).toBe(3);
  });
});
