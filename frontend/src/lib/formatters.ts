import dayjs from 'dayjs';

export const displaySymbol = (value?: string | null): string => {
  if (!value) return '';
  const s = String(value).trim();
  return s.replace(/\.NS$/i, '');
};

export const withDefaultNSExtension = (value: string): string => {
  const upper = value.trim().toUpperCase();
  return upper.endsWith('.NS') ? upper : `${upper}.NS`;
};

export const displayDate = (value?: string | number | Date | null): string => {
  if (!value) return '';
  const d = dayjs(value);
  return d.isValid() ? d.format('DD/MM/YYYY') : String(value);
};

export const displayDateTime = (value?: string | number | Date | null): string => {
  if (!value) return '';
  const d = dayjs(value);
  return d.isValid() ? d.format('DD/MM/YYYY HH:mm:ss') : String(value);
};
