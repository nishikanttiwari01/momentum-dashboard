// src/lib/hooks.ts
// Lightweight wrappers around the generated Orval client.
// They normalize AxiosResponse -> data and give us one import point.

import {
  useGetApiV1Screener,
  useGetApiV1InstrumentsSymbolDetail,
  useListRuns,
  useListAlerts,
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
  AlertState,
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
type RawAlert = AlertState | Record<string, unknown>;

export type AlertChannelFlags = Record<string, boolean>;

export type AlertListItem = {
  id: number | null;
  symbol: string;
  ruleCode: string;
  ruleValue: string | null;
  label: string;
  description: string | null;
  details: string[];
  channels: string[];
  channelFlags: AlertChannelFlags;
  enabled: boolean;
  lastScore: number | null;
  lastFiredAt: string | null;
  lastFiredLocalDate: string | null;
  lastFiredRunId: string | null;
  mutedUntil: string | null;
  createdAt: string | null;
  updatedAt: string | null;
  raw: RawAlert;
};

export function useAlerts(opts?: { staleTimeMs?: number; enabled?: boolean }) {
  const { staleTimeMs = 60_000, enabled = true } = opts ?? {};
  return useListAlerts<AlertListItem[]>({
    query: {
      select: (res) => {
        const payload = Array.isArray(res.data) ? (res.data as RawAlert[]) : [];
        return payload.map((item) => normalizeAlertRecord(item));
      },
      staleTime: staleTimeMs,
      refetchOnMount: 'always',
      refetchOnWindowFocus: true,
      refetchOnReconnect: true,
      enabled,
    },
  });
}

function normalizeAlertRecord(input: unknown): AlertListItem {
  const source = input && typeof input === 'object' ? (input as Record<string, unknown>) : {};
  const ruleCandidate =
    source['rule'] && typeof source['rule'] === 'object'
      ? (source['rule'] as Record<string, unknown>)
      : null;
  const rule = ruleCandidate && Object.keys(ruleCandidate).length > 0 ? ruleCandidate : null;

  const ruleConditions =
    rule && rule['conditions'] && typeof rule['conditions'] === 'object'
      ? (rule['conditions'] as Record<string, unknown>)
      : null;

  const symbolValue = (rule?.['symbol'] ?? source['symbol'] ?? '').toString();
  const symbol = symbolValue.toUpperCase();

  const ruleType = rule?.['rule_type'] ?? rule?.['ruleType'] ?? '';
  const ruleCodeValue =
    source['rule_code'] ??
    source['ruleCode'] ??
    ruleConditions?.['code'] ??
    ruleType ??
    '';
  const ruleCode = typeof ruleCodeValue === 'string' ? ruleCodeValue : String(ruleCodeValue ?? '');

  const ruleValueRaw = rule?.['rule_value'] ?? rule?.['ruleValue'] ?? null;
  const ruleValue =
    ruleValueRaw == null || ruleValueRaw === ''
      ? null
      : typeof ruleValueRaw === 'string'
      ? ruleValueRaw
      : String(ruleValueRaw);

  const enabledValue = rule?.['enabled'] ?? source['enabled'];
  const enabled = enabledValue === undefined ? true : Boolean(enabledValue);

  const { channelFlags, channels } = normalizeAlertChannels(
    rule?.['channels'] ?? source['channels']
  );

  const lastScore =
    toNumberLike(source['last_score']) ??
    toNumberLike(source['lastScore']) ??
    toNumberLike(ruleConditions?.['last_score']);

  const lastFiredAt = extractDateString(source, [
    'last_fired_at',
    'last_fired_at_utc',
    'lastFiredAt',
    'lastFiredAtUtc',
  ]);
  const lastFiredLocalDate = extractDateString(source, [
    'last_fired_local_date',
    'lastFiredLocalDate',
  ]);
  const lastFiredRunIdRaw =
    ruleConditions?.['last_fired_run_id'] ?? source['last_fired_run_id'] ?? source['lastFiredRunId'];
  const lastFiredRunId =
    lastFiredRunIdRaw == null || lastFiredRunIdRaw === ''
      ? null
      : typeof lastFiredRunIdRaw === 'string'
      ? lastFiredRunIdRaw
      : String(lastFiredRunIdRaw);

  const mutedUntil = extractDateString(source, ['muted_until', 'mutedUntil']);

  const details: string[] = [];
  if (ruleValue) details.push(`Value: ${ruleValue}`);
  if (lastScore !== null) details.push(`Score: ${lastScore}`);
  if (lastFiredRunId) details.push(`Run: ${lastFiredRunId}`);

  if (ruleConditions) {
    Object.entries(ruleConditions).forEach(([key, value]) => {
      if (['code', 'last_score', 'last_fired_run_id', 'last_fired_local_date'].includes(key)) return;
      const formatted = formatDetail(humanizeKey(key), value);
      if (formatted) {
        details.push(formatted);
      }
    });
  }

  const description = details.length > 0 ? details.join(' | ') : null;

  const id = toNumberLike(source['id'] ?? rule?.['id']);
  const label = ruleValue || humanizeKey(ruleCode) || 'Alert';

  return {
    id,
    symbol,
    ruleCode,
    ruleValue,
    label,
    description,
    details,
    channels,
    channelFlags,
    enabled,
    lastScore,
    lastFiredAt,
    lastFiredLocalDate,
    lastFiredRunId,
    mutedUntil,
    createdAt: null,
    updatedAt: null,
    raw: (input ?? {}) as RawAlert,
  };
}

function normalizeAlertChannels(input: unknown): {
  channelFlags: AlertChannelFlags;
  channels: string[];
} {
  const flags: AlertChannelFlags = {};

  if (Array.isArray(input)) {
    input.forEach((value) => {
      const key = typeof value === 'string' ? value : String(value ?? '');
      const normalized = key.trim().toLowerCase();
      if (!normalized) return;
      flags[normalized] = true;
    });
  } else if (input && typeof input === 'object') {
    Object.entries(input as Record<string, unknown>).forEach(([key, value]) => {
      const normalized = key.trim().toLowerCase();
      if (!normalized) return;
      flags[normalized] = Boolean(value);
    });
  } else if (typeof input === 'string') {
    const normalized = input.trim().toLowerCase();
    if (normalized) flags[normalized] = true;
  }

  const channels = Object.entries(flags)
    .filter(([, active]) => active)
    .map(([key]) => humanizeKey(key))
    .sort((a, b) => a.localeCompare(b));

  return { channelFlags: flags, channels };
}

function formatDetail(label: string, value: unknown): string | null {
  if (value === null || value === undefined) return null;

  if (typeof value === 'boolean') {
    return value ? label : null;
  }

  if (Array.isArray(value)) {
    const parts = value
      .map((part) => String(part ?? '').trim())
      .filter((part) => part.length > 0);
    if (parts.length === 0) return null;
    return `${label}: ${parts.join(', ')}`;
  }

  if (value instanceof Date) {
    return `${label}: ${value.toISOString()}`;
  }

  if (typeof value === 'object') {
    const json = JSON.stringify(value);
    if (!json || json === '{}' || json === '[]') return null;
    return `${label}: ${json}`;
  }

  const text = String(value).trim();
  if (!text) return null;
  return `${label}: ${text}`;
}

function extractDateString(source: Record<string, unknown>, keys: string[]): string | null {
  for (const key of keys) {
    const value = source[key];
    if (typeof value === 'string' && value.trim()) {
      return value;
    }
    if (value instanceof Date) {
      return value.toISOString();
    }
    if (typeof value === 'number' && Number.isFinite(value)) {
      return new Date(value).toISOString();
    }
  }
  return null;
}

function toNumberLike(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function humanizeKey(input: unknown): string {
  const str = typeof input === 'string' ? input : String(input ?? '');
  const cleaned = str.replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim();
  if (!cleaned) return '';
  const lower = cleaned.toLowerCase();
  return lower.replace(/\b\w/g, (char) => char.toUpperCase());
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


