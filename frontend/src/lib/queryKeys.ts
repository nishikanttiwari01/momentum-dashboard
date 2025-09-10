export const qk = {
  screener: ['screener'] as const,
  detail: (symbol: string) => ['detail', symbol] as const,
  alerts: ['alerts'] as const,
  history: ['history'] as const,
  settings: ['settings'] as const,
}
