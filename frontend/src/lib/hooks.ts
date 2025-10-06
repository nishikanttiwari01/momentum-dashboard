// src/lib/hooks.ts
// Lightweight wrappers around the generated Orval client.
// They normalize AxiosResponse -> data and give us one import point.

import {
  useGetApiV1Screener,
  useGetApiV1InstrumentsSymbolDetail,
  useListRuns,
} from './api/client';

import type {
  ScreenerList,
  DrawerDetail,
  GetApiV1ScreenerParams,
  GetApiV1InstrumentsSymbolDetailParams,
  ListRunsParams,
  ListRuns200,
} from './api/types';
// add
import { useListNewsBySymbol } from './api/client';
import type { ListNewsBySymbolParams, NewsListResponse } from './api/types';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';



// List news: normalized wrapper (AxiosResponse -> data)
export function useNewsList(
  params: ListNewsBySymbolParams,
  opts?: { staleTimeMs?: number }
) {
  const { staleTimeMs = 60_000 } = opts ?? {};
  return useListNewsBySymbol(params, {
    query: {
      select: (res) => res.data as NewsListResponse,
      staleTime: staleTimeMs,
      refetchOnWindowFocus: false,
    },
  });
}

/* --------------------------------------------
 * Existing hooks you already use elsewhere
 * ------------------------------------------*/
export function useScreener(
  params?: GetApiV1ScreenerParams,
  opts?: { staleTimeMs?: number }
) {
  const { staleTimeMs = 60_000 } = opts ?? {};
  return useGetApiV1Screener(params, {
    query: {
      select: (res) => res.data as ScreenerList,
      staleTime: staleTimeMs,
      refetchOnWindowFocus: true,
    },
  });
}

export function useInstrumentDetail(
  symbol: string,
  params?: GetApiV1InstrumentsSymbolDetailParams,
  opts?: { enabled?: boolean; staleTimeMs?: number }
) {
  const { enabled = true, staleTimeMs = 60_000 } = opts ?? {};
  return useGetApiV1InstrumentsSymbolDetail(symbol, params, {
    query: {
      select: (res) => res.data as DrawerDetail,
      enabled: !!symbol && enabled,
      staleTime: staleTimeMs,
      refetchOnWindowFocus: true,
    },
  });
}

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

/* --------------------------------------------
 * New: Positions (Lock / Unlock) for RightDrawer
 * Uses fetch + React Query to avoid depending on
 * generated names from Orval.
 * ------------------------------------------*/

export type PositionOut = {
  id: number;
  symbol: string;
  entry_price_locked?: number | null;
  qty?: number | null;
  stop_now?: number | null;
  exit_close_threshold?: number | null;
  breakeven_active?: boolean;
  euphoria_on?: boolean;
  trade_on?: boolean;
  note?: string | null;
  created_at?: string;
  updated_at?: string;
};

export type PositionIn = {
  symbol: string;
  price: number;
  as_of?: string;
  note?: string;
};

// Source of truth for a single symbol's saved/locked position
export function usePosition(symbol: string, opts?: { enabled?: boolean }) {
  const enabled = !!symbol && (opts?.enabled ?? true);
  return useQuery({
    queryKey: ['position', symbol],
    enabled,
    staleTime: 60_000,
    refetchOnWindowFocus: true,
    queryFn: async (): Promise<PositionOut | undefined> => {
      const res = await fetch(`/api/v1/positions/${encodeURIComponent(symbol)}`);
      if (res.status === 404) return undefined; // no saved position yet
      if (!res.ok) throw new Error(`Failed to load position: ${res.status}`);
      return res.json();
    },
  });
}

// Lock trade (create or set entry_price_locked)
export function useLockPosition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ data }: { data: PositionIn }) => {
      const res = await fetch(`/api/v1/positions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      if (!res.ok) throw new Error(`Lock failed: ${res.status}`);
      return (await res.json()) as PositionOut;
    },
    onSuccess: (pos) => {
      // Refresh this symbol's position cache if present
      if (pos?.symbol) {
        qc.invalidateQueries({ queryKey: ['position', pos.symbol] });
      }
    },
  });
}

// Unlock trade (delete position row)
export function useUnlockPosition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id }: { id: number }) => {
      const res = await fetch(`/api/v1/positions/${id}`, { method: 'DELETE' });
      // 204 is expected; some stacks still return 200 with empty body
      if (!(res.status === 204 || res.ok)) {
        throw new Error(`Unlock failed: ${res.status}`);
      }
      return id;
    },
    // Caller refetches detail/position; we don't know the symbol here
    onSuccess: () => {
      // optional: could invalidate all 'position' queries, but not necessary
      // qc.invalidateQueries({ queryKey: ['position'] });
    },
  });
}

// Handy helper if you want to invalidate manually from components
export function invalidatePositionQueryKey(symbol: string) {
  return ['position', symbol] as const;
}
