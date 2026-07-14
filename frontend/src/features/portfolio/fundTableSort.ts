export type FundSortKey =
  | 'fund'
  | 'category'
  | 'nav'
  | 'return1m'
  | 'return6m'
  | 'return1y'
  | 'drawdown'
  | 'invested'
  | 'value'
  | 'xirr'
  | 'averageNav'
  | 'gain';

export type SortDirection = 'asc' | 'desc';

export type FundSortRecord = {
  id: string;
  name: string;
  category: string;
  performance?: {
    latest_nav?: number | null;
    ret_1m_pct?: number | null;
    ret_6m_pct?: number | null;
    ret_1y_pct?: number | null;
    drawdown_from_1y_high_pct?: number | null;
  };
  totals?: {
    invested?: number | null;
    current_value?: number | null;
    xirr_pct?: number | null;
  } | null;
  combined_holding?: {
    average_nav?: number | null;
    gain?: number | null;
  } | null;
};

const valueFor = (fund: FundSortRecord, key: FundSortKey): string | number | null | undefined => {
  switch (key) {
    case 'fund': return fund.name;
    case 'category': return fund.category;
    case 'nav': return fund.performance?.latest_nav;
    case 'return1m': return fund.performance?.ret_1m_pct;
    case 'return6m': return fund.performance?.ret_6m_pct;
    case 'return1y': return fund.performance?.ret_1y_pct;
    case 'drawdown': return fund.performance?.drawdown_from_1y_high_pct;
    case 'invested': return fund.totals?.invested;
    case 'value': return fund.totals?.current_value;
    case 'xirr': return fund.totals?.xirr_pct;
    case 'averageNav': return fund.combined_holding?.average_nav;
    case 'gain': return fund.combined_holding?.gain;
  }
};

const isMissing = (value: string | number | null | undefined) =>
  value == null || (typeof value === 'number' && !Number.isFinite(value));

export const sortFunds = <T extends FundSortRecord>(
  funds: readonly T[],
  key: FundSortKey | null,
  direction: SortDirection,
): T[] => {
  if (key == null) return [...funds];

  return funds
    .map((fund, index) => ({ fund, index, value: valueFor(fund, key) }))
    .sort((left, right) => {
      const leftMissing = isMissing(left.value);
      const rightMissing = isMissing(right.value);
      if (leftMissing !== rightMissing) return leftMissing ? 1 : -1;
      if (leftMissing && rightMissing) return left.index - right.index;

      const comparison = typeof left.value === 'string' && typeof right.value === 'string'
        ? left.value.localeCompare(right.value, undefined, { sensitivity: 'base' })
        : Number(left.value) - Number(right.value);
      return comparison === 0
        ? left.index - right.index
        : direction === 'asc' ? comparison : -comparison;
    })
    .map(({ fund }) => fund);
};
