// Lightweight wrappers around the generated Orval client.
// They normalize AxiosResponse -> data and give us one import point.

import {
  useGetScreener,
  useGetInstrumentsSymbolDetail,
  useListRuns,
} from './api/client';

import type {
  ScreenerList,
  DrawerDetail,
  GetScreenerParams,
  GetInstrumentsSymbolDetailParams,
  ListRunsParams,
  ListRuns200,
} from './api/types';

// --- Screener (table) ---
export function useScreener(
  params?: GetScreenerParams,
  opts?: {
    // react-query overrides if you need them on a call-site (optional)
    staleTimeMs?: number;
    refetchIntervalMs?: number | false;
  }
) {
  const { staleTimeMs = 30_000, refetchIntervalMs = false } = opts ?? {};

  return useGetScreener(params, {
    // Always return .data (ScreenerList), not AxiosResponse
    query: {
      select: (res) => res.data as ScreenerList,
      staleTime: staleTimeMs,
      refetchInterval: refetchIntervalMs,
      refetchOnWindowFocus: true,
      keepPreviousData: true,
    },
  });
}

// --- Instrument Detail (Right Drawer) ---
export function useInstrumentDetail(
  symbol: string,
  params?: GetInstrumentsSymbolDetailParams,
  opts?: {
    staleTimeMs?: number;
    enabled?: boolean; // let the caller decide when to fetch (e.g., only if a symbol is selected)
  }
) {
  const { staleTimeMs = 60_000, enabled = true } = opts ?? {};

  return useGetInstrumentsSymbolDetail(symbol, params, {
    query: {
      enabled,
      select: (res) => res.data as DrawerDetail,
      staleTime: staleTimeMs,
      refetchOnWindowFocus: true,
    },
  });
}

// --- Runs list (for the run selector in AppBar), handy soon ---
export function useRuns(
  params?: ListRunsParams,
  opts?: { staleTimeMs?: number }
) {
  const { staleTimeMs = 60_000 } = opts ?? {};
  return useListRuns(params, {
    query: {
      select: (res) => res.data as ListRuns200,
      staleTime: staleTimeMs,
      refetchOnWindowFocus: true,
    },
  });
}
