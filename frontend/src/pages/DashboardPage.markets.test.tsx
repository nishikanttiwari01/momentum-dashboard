// @vitest-environment jsdom
import * as React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import DashboardPage from './DashboardPage';

vi.mock('react-router-dom', () => ({ useOutletContext: () => ({ refetchIntervalMs: 0 }) }));
vi.mock('@tanstack/react-query', () => ({
  useQuery: () => ({ data: undefined }),
  useQueries: () => [],
}));
vi.mock('@/lib/api/client', () => ({
  getGetApiV1InstrumentsSymbolDetailQueryOptions: vi.fn(),
  useGetApiV1Positions: () => ({ data: undefined, isLoading: false, isError: false }),
  useGetTopMovers: () => ({ data: undefined, isLoading: false, isError: false }),
  useGetCandidatePool: () => ({ data: undefined, isLoading: false, isError: false }),
}));

vi.mock('../components/DataHealthPanel', () => ({ default: () => <div data-testid="data-health" /> }));
vi.mock('../components/MarketIndexChartCard', () => ({
  default: ({ marketKey }: { marketKey: string }) => <div data-testid={`market-${marketKey}`} />,
}));
vi.mock('../components/TradePositionsPanel', () => ({ default: () => <div data-testid="investments" /> }));
vi.mock('../components/SectorHeatmap', () => ({ default: () => null }));
vi.mock('../components/AccumulationWatchCard', () => ({ default: () => null }));
vi.mock('../components/EtfWatchCard', () => ({ default: () => null }));
vi.mock('../components/RelevantNewsCard', () => ({ default: () => null }));
vi.mock('@/features/detail/RightDrawer', () => ({ default: () => null }));

afterEach(cleanup);

describe('DashboardPage markets composition', () => {
  it('renders semantic section order and both market cards', () => {
    render(<DashboardPage />);

    const dataHealth = screen.getByTestId('data-health');
    const marketsHeading = screen.getByRole('heading', { level: 2, name: 'Markets — India & US' });
    const investmentsHeading = screen.getByRole('heading', { level: 2, name: 'My investments — open trades' });
    const sensex = screen.getByTestId('market-sensex');
    const sp500 = screen.getByTestId('market-sp500');

    expect(marketsHeading.id).toBe('markets-heading');
    expect(sensex.closest('[aria-labelledby="markets-heading"]')).toBeTruthy();
    expect(screen.getByTestId('investments').closest('[aria-labelledby="investments-heading"]')).toBeTruthy();
    expect(dataHealth.compareDocumentPosition(marketsHeading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(marketsHeading.compareDocumentPosition(investmentsHeading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(marketsHeading.compareDocumentPosition(sensex) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(sensex.compareDocumentPosition(sp500) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(sp500.compareDocumentPosition(investmentsHeading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
