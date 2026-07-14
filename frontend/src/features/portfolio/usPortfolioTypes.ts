export type UsTransaction = {
  id: string; instrument_id: string; purchased_at: string; quantity: number;
  price_usd: number; fees_usd: number; invested_usd: number;
};

export type UsInstrument = {
  id: string; ticker: string; name: string; currency: 'USD';
  latest_price_usd: number | null; latest_price_date: string | null;
  holding: {
    total_units: number; total_invested_usd: number; average_buy_price_usd: number | null;
    current_value_usd: number | null; unrealized_gain_usd: number | null; unrealized_gain_pct: number | null;
  };
  transactions: UsTransaction[]; market_data_error: string | null;
};

export type UsOverview = { generated_at: string; currency: 'USD'; instruments: UsInstrument[] };
export type UsHistory = {
  instrument_id: string; range: string; points: { date: string; price: number }[];
  purchases: UsTransaction[]; average_buy_price_usd: number | null;
  latest_vs_average_pct: number | null; error: string | null;
};

export const usd = (value?: number | null) => value == null ? '—' : new Intl.NumberFormat(
  'en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 }
).format(value);
