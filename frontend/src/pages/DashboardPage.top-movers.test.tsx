// @vitest-environment jsdom
import * as React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import DashboardPage from './DashboardPage';

const { topMoversHook, drawerProps, hookResult } = vi.hoisted(() => ({
  topMoversHook: vi.fn(),
  drawerProps: vi.fn(),
  hookResult: { current: undefined as unknown },
}));

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
vi.mock('@/features/detail/RightDrawer', () => ({
  default: (props: unknown) => { drawerProps(props); return <div data-testid="right-drawer" />; },
}));

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
  hookResult.current = {
    data: { data: moversData },
    isLoading: false,
    isError: false,
  };
  topMoversHook.mockImplementation(() => hookResult.current);
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
    expect(screen.getByRole('group', { name: 'Top Movers period' })).toBeTruthy();
    expect(screen.getByTestId('top-movers-period-scroll').style.overflowX).toBe('auto');
  });

  it('keeps custom draft dates out of the applied query until a valid Apply', () => {
    render(<DashboardPage />);
    fireEvent.click(screen.getByRole('button', { name: 'Custom' }));
    expect(topMoversHook.mock.calls.at(-1)?.[0]).toEqual({ period: '1d' });

    fireEvent.change(screen.getByLabelText('Start date'), { target: { value: '2026-07-12' } });
    fireEvent.change(screen.getByLabelText('End date'), { target: { value: '2026-07-10' } });
    expect(topMoversHook.mock.calls.at(-1)?.[0]).toEqual({ period: '1d' });
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
    const error = screen.getByRole('alert');
    expect(error.textContent).toBe('Start date must be on or before end date');
    expect(screen.getByLabelText('Start date').getAttribute('aria-invalid')).toBe('true');
    expect(screen.getByLabelText('End date').getAttribute('aria-invalid')).toBe('true');
    expect(screen.getByLabelText('Start date').getAttribute('aria-describedby')).toBe(error.id);
    expect(screen.getByLabelText('End date').getAttribute('aria-describedby')).toBe(error.id);
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

  it('renders retained mover data while loading and opens the drawer for the clicked symbol', () => {
    hookResult.current = {
      data: {
        data: {
          ...moversData,
          gainers: [{ symbol: 'RELIANCE.NS', name: 'Reliance', price: 3000, change_pct: 4.2, score: 88 }],
          losers: [{ symbol: 'TCS.NS', name: 'TCS', price: 4000, change_pct: -2.1, score: 72 }],
        },
      },
      isLoading: true,
      isError: false,
    };
    render(<DashboardPage />);

    expect(screen.getByText('RELIANCE')).toBeTruthy();
    expect(screen.getAllByText('TCS').length).toBeGreaterThan(0);
    fireEvent.click(screen.getByText('RELIANCE'));
    expect(drawerProps.mock.calls.at(-1)?.[0]).toMatchObject({
      symbol: 'RELIANCE.NS', open: true, asOf: '2026-07-16',
    });
  });

  it('shows clear empty states for both mover lists after a successful empty response', () => {
    hookResult.current = {
      data: { data: { ...moversData, gainers: [], losers: [] } },
      isLoading: false,
      isError: false,
    };
    render(<DashboardPage />);

    expect(screen.getByRole('heading', { name: 'Top Gainers' })).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'Top Losers' })).toBeTruthy();
    expect(screen.getAllByText('No data available')).toHaveLength(2);
    expect(screen.queryByRole('progressbar')).toBeNull();
    expect(screen.queryByText('Unable to load top movers right now.')).toBeNull();
  });
});
