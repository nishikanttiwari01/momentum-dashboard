// @vitest-environment jsdom
import * as React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import axios from 'axios';
import { afterEach, describe, expect, it, vi } from 'vitest';
import MarketIndexChartCard from './MarketIndexChartCard';

const { lineSpy, yAxisSpy } = vi.hoisted(() => ({ lineSpy: vi.fn(), yAxisSpy: vi.fn() }));

vi.mock('axios');
vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  LineChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Line: (props: unknown) => { lineSpy(props); return null; },
  XAxis: () => null,
  YAxis: (props: unknown) => { yAxisSpy(props); return null; },
  Tooltip: () => null,
  CartesianGrid: () => null,
}));

const mockedAxios = vi.mocked(axios, true);

const payload = {
  key: 'sensex',
  name: 'S&P BSE Sensex',
  symbol: '^BSESN',
  range: '1y',
  latest_value: 81234.56,
  change: 1234.5,
  change_pct: 1.54,
  points: [
    { on: '2025-07-16', close: 80000.06 },
    { on: '2026-07-16', close: 81234.56 },
  ],
};

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MarketIndexChartCard marketKey="sensex" />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('MarketIndexChartCard', () => {
  it('shows the index title, latest value, and selected-period change', async () => {
    mockedAxios.get.mockResolvedValue({ data: payload });
    renderCard();

    expect(await screen.findByText('S&P BSE Sensex')).toBeTruthy();
    expect(screen.getByText('^BSESN')).toBeTruthy();
    expect(screen.getByText('81,234.56')).toBeTruthy();
    expect(screen.getByText('+1,234.50 (+1.54%)')).toBeTruthy();
    expect(mockedAxios.get).toHaveBeenCalledWith('/api/v1/market-indices/sensex/history', {
      params: { range: '1y' },
    });
    expect(lineSpy).toHaveBeenCalledWith(expect.objectContaining({ type: 'linear', stroke: '#2E90FA' }));
  });

  it('styles a negative change and gives a constant zero series a non-degenerate domain', async () => {
    mockedAxios.get.mockResolvedValue({
      data: {
        ...payload,
        change: -25,
        change_pct: -0.5,
        points: [{ on: '2026-07-16', close: 0 }],
      },
    });
    renderCard();

    const change = await screen.findByText('-25.00 (-0.50%)');
    expect(getComputedStyle(change).color).toBe('rgb(240, 68, 56)');
    const domain = yAxisSpy.mock.calls.at(-1)?.[0].domain as [number, number];
    expect(domain[0]).toBeLessThan(domain[1]);
  });

  it('requests six-month history when 6M is selected', async () => {
    mockedAxios.get.mockResolvedValue({ data: payload });
    renderCard();
    await screen.findByText('S&P BSE Sensex');

    fireEvent.click(screen.getByRole('button', { name: 'Show 6M history' }));

    await waitFor(() =>
      expect(mockedAxios.get).toHaveBeenLastCalledWith('/api/v1/market-indices/sensex/history', {
        params: { range: '6m' },
      }),
    );
  });

  it('preserves the card and retries an unavailable index', async () => {
    mockedAxios.get
      .mockRejectedValueOnce(new Error('offline'))
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce({ data: payload });
    renderCard();

    expect(await screen.findByText('Market index unavailable')).toBeTruthy();
    const card = screen.getByTestId('market-index-chart-card');
    expect(getComputedStyle(card).minHeight).toBe('330px');

    fireEvent.click(screen.getByRole('button', { name: 'Retry loading SENSEX market index' }));

    expect(await screen.findByText('S&P BSE Sensex')).toBeTruthy();
    expect(mockedAxios.get).toHaveBeenCalledTimes(3);
  });
});
