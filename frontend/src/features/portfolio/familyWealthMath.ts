import type {
  AnnualRunwayEvent,
  FamilyGoalHealthStatus,
  FamilyScenarioProjection,
  ProblemLocationPart,
} from './wealthTypes';

export type FamilyRunwayEvent = AnnualRunwayEvent & { label: string };

export type FamilyRunwayRow = {
  on: string;
  year: number;
  conservative_total_inr?: number;
  expected_total_inr?: number;
  optimistic_total_inr?: number;
  expected_financial_assets_inr?: number;
  expected_property_value_inr?: number;
  events: FamilyRunwayEvent[];
};

export function familyRunwayRows(projections: readonly FamilyScenarioProjection[]): FamilyRunwayRow[] {
  const rows = new Map<string, FamilyRunwayRow>();
  for (const projection of projections) {
    const scenario = projection.settings.scenario_key;
    for (const point of projection.annual_points) {
      const row = rows.get(point.on) ?? {
        on: point.on,
        year: Number(point.on.slice(0, 4)),
        events: [],
      };
      row[`${scenario}_total_inr`] = point.total_net_worth_inr;
      if (scenario === 'expected') {
        row.expected_financial_assets_inr = point.financial_assets_inr;
        row.expected_property_value_inr = point.property_value_inr;
        row.events = point.events.map((event) => ({ ...event, label: event.goal_name }));
      }
      rows.set(point.on, row);
    }
  }
  return [...rows.values()].sort((left, right) => left.on.localeCompare(right.on));
}

const STATUS_COLORS: Record<FamilyGoalHealthStatus, string> = {
  green: '#137333', amber: '#9A6700', red: '#B3261E',
};

export function goalStatusColor(status: FamilyGoalHealthStatus): string {
  return STATUS_COLORS[status];
}

function trimFraction(value: number): string {
  return value.toFixed(2).replace(/\.00$/, '').replace(/(\.\d)0$/, '$1');
}

export function formatCrore(value: number | null | undefined): string {
  if (value == null) return '—';
  if (value === 0) return '₹0';
  const sign = value < 0 ? '-' : '';
  return `${sign}₹${trimFraction(Math.abs(value) / 10_000_000)} Cr`;
}

export function formatMonthlyIncome(value: number | null | undefined): string {
  if (value == null) return '—';
  const sign = value < 0 ? '-' : '';
  const amount = Math.abs(value).toLocaleString('en-IN', { maximumFractionDigits: 0 });
  return `${sign}₹${amount}/month`;
}

export function familyPlanProblemField(loc: readonly ProblemLocationPart[]): string | null {
  const path = loc[0] === 'body' ? loc.slice(1) : loc;
  if (!['assumptions', 'goals', 'scenarios'].includes(String(path[0]))) return null;
  return path.map(String).join('.');
}
