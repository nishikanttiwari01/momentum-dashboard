// @vitest-environment jsdom
import * as React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import DashboardPage from './DashboardPage';

const { topMoversHook } = vi.hoisted(() => ({ topMoversHook: vi.fn() }));

vi.mock('react-router-dom', () => ({ useOutletContext: () => ({ refetchIntervalMs: 0 }) }));
vi.mock('@tanstack/react-query', () => ({ useQuery: () => ({ data: undefined }), useQueries: () => [] }));
vi.mock('@/lib/api/client', () => ({
  getGetApiV1InstrumentsSymbolDetailQueryOptions: vi.fn(),
  useGetApiV1Positions: () => ({ data: undefined, isLoading: false, isError: false }),
  useGetTopMovers: topMoversHook,
  useGetCandidatePool: () => ({ data: undefined, isLoading: false, isError: false }),
}));
vi.mock('../components/DataHealthPanel', () => ({ default: () => null }));
vi.mock('../components/MarketIndexChartCard', () => ({ default: () => null }));
vi.mock('../components/TradePositionsPanel', () => ({ default: () => null }));
vi.mock('../components/SectorHeatmap', () => ({ default: () => null }));
vi.mock('../components/AccumulationWatchCard', () => ({ default: () => null }));
vi.mock('../components/EtfWatchCard', () => ({ default: () => <div>ETF Watch</div> }));
vi.mock('../components/RelevantNewsCard', () => ({ default: () => null }));
vi.mock('@/features/detail/RightDrawer', () => ({ default: () => null }));

const moversData = {
  as_of: '2026-07-16',
  generated_at: '2026-07-17T08:00:00Z',
  period: '1d',
  resolved_start_date: '2026-07-10',
  resolved_end_date: '2026-07-16',
  gainers: [],
  losers: [],
};

beforeEach(() => {
  topMoversHook.mockImplementation(() => ({
    data: { data: moversData },
    isLoading: false,
    isError: false,
  }));
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe('DashboardPage top movers controls', () => {
  it('renders every period control, resolved dates, and the consolidated market layout', () => {
    render(<DashboardPage />);

    for (const label of ['1 Day', '1 Week', '1 Month', '3 Months', '6 Months', '1 Year', '5 Years', 'Custom']) {
      expect(screen.getByRole('button', { name: label })).toBeTruthy();
    }
    expect(screen.queryByText('Top Performers')).toBeNull();
    expect(screen.getByText(/2026-07-10.*2026-07-16/)).toBeTruthy();
    expect(screen.getByTestId('etf-watch-grid').className).toContain('MuiGrid-grid-lg-12');
  });

  it('keeps custom draft dates out of the applied query until a valid Apply', () => {
    render(<DashboardPage />);
    fireEvent.click(screen.getByRole('button', { name: 'Custom' }));
    expect(topMoversHook.mock.calls.at(-1)?.[0]).toEqual({ period: '1d' });

    fireEvent.change(screen.getByLabelText('Start date'), { target: { value: '2026-07-12' } });
    fireEvent.change(screen.getByLabelText('End date'), { target: { value: '2026-07-10' } });
    expect(topMoversHook.mock.calls.at(-1)?.[0]).toEqual({ period: '1d' });
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
    expect(screen.getByText('Start date must be on or before end date')).toBeTruthy();
    expect(topMoversHook.mock.calls.at(-1)?.[0]).toEqual({ period: '1d' });

    fireEvent.change(screen.getByLabelText('End date'), { target: { value: '2026-07-15' } });
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
    expect(topMoversHook.mock.calls.at(-1)?.[0]).toEqual({
      period: 'custom', start_date: '2026-07-12', end_date: '2026-07-15',
    });
  });

  it('clears applied custom dates when a preset is selected', () => {
    render(<DashboardPage />);
    fireEvent.click(screen.getByRole('button', { name: 'Custom' }));
    fireEvent.change(screen.getByLabelText('Start date'), { target: { value: '2026-07-01' } });
    fireEvent.change(screen.getByLabelText('End date'), { target: { value: '2026-07-15' } });
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
    fireEvent.click(screen.getByRole('button', { name: '6 Months' }));
    expect(topMoversHook.mock.calls.at(-1)?.[0]).toEqual({ period: '6m' });
    expect(screen.queryByLabelText('Start date')).toBeNull();
  });
});
