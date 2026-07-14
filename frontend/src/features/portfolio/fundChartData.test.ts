import { describe, expect, it } from 'vitest';
import { buildFundChartSeries, getFundChartDomain } from './fundChartData';

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

  it('uses the full NAV history for the domain instead of purchase dates', () => {
    const prices = [
      { time: Date.parse('2021-01-01T00:00:00Z'), fullDate: '2021-01-01', nav: 50 },
      { time: Date.parse('2026-01-01T00:00:00Z'), fullDate: '2026-01-01', nav: 100 },
    ];
    expect(getFundChartDomain(prices)).toEqual([prices[0].time, prices[1].time]);
  });
});
