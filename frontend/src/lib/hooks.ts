// src/lib/hooks.ts
// Lightweight wrappers around the generated Orval client.
// They normalize AxiosResponse -> data and give us one import point.

import {
  useGetApiV1Screener,
  useGetApiV1InstrumentsSymbolDetail,
  useListRuns,
  useListAlertEvents,
  useListNewsBySymbol,
  useListAllNews,
  listAllNews,
} from './api/client';

import type {
  ScreenerList,
  DrawerDetail,
  GetApiV1ScreenerParams,
  GetApiV1InstrumentsSymbolDetailParams,
  ListRunsParams,
  ListRuns200,
  ListNewsBySymbolParams,
  ListAllNewsParams,
  NewsListResponse,
  NewsWindowListResponse,
  AlertEvent,
  AlertEventDigestBucket,
  AlertEventMode,
  AlertEventSendType,
  AlertEventSeverity,
  AlertEventTriggeredBy,
  AlertChannelStatus,
  AlertDeliveryAttempt,
  ListAlertEventsParams,
} from './api/types';
import { useQuery, useMutation, useQueryClient, useInfiniteQuery } from '@tanstack/react-query';



// List news: normalized wrapper (AxiosResponse -> data)
export function useNewsList(
  params: ListNewsBySymbolParams,
  opts?: { staleTimeMs?: number; enabled?: boolean }
) {
  const { staleTimeMs = 60_000, enabled = true } = opts ?? {};
  return useListNewsBySymbol(params, {
    query: {
      select: (res) => res.data as NewsListResponse,
      staleTime: staleTimeMs,
      refetchOnWindowFocus: false,
      enabled,
    },
  });
}

export function useAllNews(
  params?: ListAllNewsParams,
  opts?: { staleTimeMs?: number; enabled?: boolean }
) {
  const { staleTimeMs = 60_000, enabled = true } = opts ?? {};
  return useListAllNews(params, {
    query: {
      select: (res) => res.data as NewsWindowListResponse,
      staleTime: staleTimeMs,
      refetchOnWindowFocus: false,
      enabled,
    },
  });
}

export function useAllNewsInfinite(
  params?: Omit<ListAllNewsParams, 'page' | 'per_page'> & { per_page?: number },
  opts?: { perPage?: number; staleTimeMs?: number; enabled?: boolean }
) {
  const { perPage = 200, staleTimeMs = 60_000, enabled = true } = opts ?? {};
  return useInfiniteQuery({
    queryKey: ['all-news', params, perPage],
    enabled: !!params && enabled,
    staleTime: staleTimeMs,
    refetchOnWindowFocus: false,
    initialPageParam: 1,
    getNextPageParam: (lastPage) => lastPage.next_page ?? undefined,
    queryFn: async ({ pageParam }) => {
      if (!params) {
        throw new Error('params required');
      }
      const response = await listAllNews({
        ...params,
        page: pageParam as number,
        per_page: perPage,
      });
      return response.data as NewsWindowListResponse;
    },
  });
}

/* --------------------------------------------
 * Alerts
 * ------------------------------------------*/
type RawAlertEvent = AlertEvent | Record<string, unknown>;

export type AlertEventListItem = {
  id: number;
  symbol: string;
  firedAtUtc: string;
  tradingDate: string;
  intradayBucketLabel: string | null;
  bucketOrd: number;
  mode: AlertEventMode;
  title: string;
  body: string;
  severity: AlertEventSeverity;
  digestBucket: AlertEventDigestBucket;
  sendType: AlertEventSendType;
  digestId: string | null;
  scoreAtFire: number | null;
  nextActionCode: string | null;
  triggeredBy?: AlertEventTriggeredBy;
  profile: string | null;
  configVersion: number | null;
  channelsSummary: Record<string, AlertChannelStatus>;
  deliveries: AlertDeliveryAttempt[];
  context: Record<string, unknown>;
  details: Record<string, unknown>;
  raw: AlertEvent;
};

export function useAlerts(
  params?: ListAlertEventsParams,
  opts?: { staleTimeMs?: number; enabled?: boolean }
) {
  const { staleTimeMs = 60_000, enabled = true } = opts ?? {};
  return useListAlertEvents<AlertEventListItem[]>(params, {
    query: {
      select: (res) => {
        const payload = Array.isArray(res.data) ? (res.data as RawAlertEvent[]) : [];
        return payload
          .map((item) => normalizeAlertEvent(item))
          .filter((item): item is AlertEventListItem => item !== null);
      },
      staleTime: staleTimeMs,
      refetchOnWindowFocus: true,
      refetchOnReconnect: true,
      enabled,
    },
  });
}

function normalizeAlertEvent(input: RawAlertEvent): AlertEventListItem | null {
  if (!input || typeof input !== 'object') return null;
  const source = input as AlertEvent;
  if (typeof source.id !== 'number' || typeof source.fired_at_utc !== 'string') {
    return null;
  }

  const channelsSummary = normalizeChannelSummary(source.channels_summary_json);
  const deliveries = normalizeDeliveries(source.deliveries);
  const context = normalizeDictionary(source.context_json);
  const details = normalizeDictionary(source.details_json);

  return {
    id: source.id,
    symbol: (source.symbol ?? '').toUpperCase(),
    firedAtUtc: source.fired_at_utc,
    tradingDate: source.trading_date ?? '',
    intradayBucketLabel: source.intraday_bucket_label ?? null,
    bucketOrd: source.bucket_ord ?? 0,
    mode: source.mode,
    title: source.title_rendered ?? '',
    body: source.body_rendered ?? '',
    severity: source.severity,
    digestBucket: source.digest_bucket,
    sendType: source.send_type,
    digestId: source.digest_id ?? null,
    scoreAtFire: source.score_at_fire ?? null,
    nextActionCode: source.next_action_code ?? null,
    triggeredBy: source.triggered_by,
    profile: source.profile ?? null,
    configVersion: source.config_version ?? null,
    channelsSummary,
    deliveries,
    context,
    details,
    raw: source,
  };
}

function normalizeChannelSummary(
  input: AlertEvent['channels_summary_json']
): Record<string, AlertChannelStatus> {
  const out: Record<string, AlertChannelStatus> = {};
  if (!input || typeof input !== 'object') {
    return out;
  }
  Object.entries(input).forEach(([key, value]) => {
    if (value && typeof value === 'object') {
      out[key] = {
        status: value.status,
        attempts: value.attempts ?? null,
        code: value.code ?? null,
        reason: value.reason ?? null,
      };
    }
  });
  return out;
}

function normalizeDictionary(input: unknown): Record<string, unknown> {
  if (!input || typeof input !== 'object' || Array.isArray(input)) {
    return {};
  }
  return { ...(input as Record<string, unknown>) };
}

function normalizeDeliveries(input: AlertEvent['deliveries']): AlertDeliveryAttempt[] {
  if (!Array.isArray(input)) {
    return [];
  }
  return input
    .filter((item): item is AlertDeliveryAttempt => !!item && typeof item === 'object')
    .map((item) => ({
      channel: item.channel ?? '',
      status: item.status,
      attempt_no: item.attempt_no ?? 1,
      sent_at_utc: item.sent_at_utc ?? null,
      response_code: item.response_code ?? null,
      response_meta: item.response_meta ?? undefined,
    }));
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
   sell_price?: number | null;
   sold_at?: string | null;
   realized_pl?: number | null;
   realized_pl_pct?: number | null;
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
    queryFn: async (): Promise<PositionOut | null> => {
      const res = await fetch(`/api/v1/positions/${encodeURIComponent(symbol)}`);
      if (res.status === 404) return null; // no saved position yet
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

// Close trade (mark inactive with sell info)
export function useUnlockPosition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, data }: { id: number; data: Partial<PositionOut> }) => {
      const res = await fetch(`/api/v1/positions/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      if (!res.ok) {
        const detail = await res.text().catch(() => '');
        throw new Error(detail || `Unlock failed: ${res.status}`);
      }
      return (await res.json()) as PositionOut;
    },
    onSuccess: (pos) => {
      if (pos?.symbol) {
        qc.invalidateQueries({ queryKey: ['position', pos.symbol] });
      }
    },
  });
}

// Handy helper if you want to invalidate manually from components
export function invalidatePositionQueryKey(symbol: string) {
  return ['position', symbol] as const;
}


