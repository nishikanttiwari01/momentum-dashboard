// small formatting helpers shared by drawer components
export const pct = (v?: number, digits = 2) =>
  typeof v === 'number' && isFinite(v) ? `${v.toFixed(digits)}%` : '—';

export const rup = (v?: number, digits = 2) =>
  typeof v === 'number' && isFinite(v) ? `₹${v.toFixed(digits)}` : '—';

export const num = (v?: number, digits = 2) =>
  typeof v === 'number' && isFinite(v) ? v.toFixed(digits) : '—';

export const relvol = (v?: number) =>
  typeof v === 'number' && isFinite(v) ? `${v.toFixed(2)}×` : '—';

export const prox52w = (p?: number) => {
  if (typeof p !== 'number' || !isFinite(p)) return '—';
  if (p === 0) return 'At 52W high';
  return p > 0 ? `${pct(p)} above` : `${pct(Math.abs(p))} below`;
};

export const levelColor = (level?: string) => {
  switch ((level || '').toLowerCase()) {
    case 'low':
      return 'success';
    case 'medium':
      return 'warning';
    case 'high':
      return 'error';
    default:
      return 'default';
  }
};

export type AnyRec = Record<string, any>;
