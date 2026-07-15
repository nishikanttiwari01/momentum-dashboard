import React from 'react';
import { Box, Chip, Stack, Typography } from '@mui/material';
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { familyRunwayRows, formatCrore, type FamilyRunwayEvent } from './familyWealthMath';
import type { AnnualRunwayEvent, AnnualRunwayPoint, FamilyScenarioProjection } from './wealthTypes';

export const RUNWAY_LINE_COLORS = { total: '#102A43', financial: '#2563EB', property: '#0F9D8A', conservative: '#D98A00', optimistic: '#7357B6' } as const;
export const RUNWAY_LINE_ANIMATION_ACTIVE = false;

export function aggregateRunwayEvents(events: readonly AnnualRunwayEvent[]): { label: string; events: AnnualRunwayEvent[] }[] {
  if (!events.length) return [];
  return [{ label: events.length === 1 ? events[0].goal_name : `${events.length} milestones`, events: [...events] }];
}

export function runwayTooltipLines(point: AnnualRunwayPoint): string[] {
  return [
    `Total net worth ${formatCrore(point.total_net_worth_inr)}`,
    `Financial assets ${formatCrore(point.financial_assets_inr)}`,
    `Property value ${formatCrore(point.property_value_inr)}`,
    `Annual contributions ${formatCrore(point.annual_contributions_inr)}`,
    `Rent ${formatCrore(point.annual_rent_inr)}`,
    `Financial growth ${formatCrore(point.financial_growth_inr)}`,
    `Property growth ${formatCrore(point.property_growth_inr)}`,
    `Goal outflows ${formatCrore(point.goal_outflows_inr)}`,
    ...point.events.map((event) => `${event.goal_name}: funded ${formatCrore(event.funded_amount_inr)}${event.shortfall_inr > 0 ? `; shortfall ${formatCrore(event.shortfall_inr)}` : ''}`),
  ];
}

export const RunwayTooltipContent = ({ active, label, payload, pointByDate }: { active?: boolean; label?: string; payload?: unknown[]; pointByDate: Map<string, AnnualRunwayPoint> }) => {
  if (!active || !payload?.length || !label) return null;
  const point = pointByDate.get(label);
  if (!point) return null;
  return <Box sx={{ bgcolor: '#fff', border: '1px solid #D9E5F2', borderRadius: 2, p: 1.5, boxShadow: '0 8px 24px rgba(16,42,67,.12)' }}>
    <Typography variant="subtitle2">Year ending {point.on}</Typography>
    {runwayTooltipLines(point).map((line, index) => <Typography key={line} variant="caption" display="block" sx={index >= 8 ? { color: line.includes('shortfall') ? '#DC4C4C' : '#0F766E', mt: .5 } : undefined}>{line}</Typography>)}
  </Box>;
};

export const FamilyWealthRunwayChart: React.FC<{ projections: readonly FamilyScenarioProjection[] }> = ({ projections }) => {
  const rows = familyRunwayRows(projections);
  const expected = projections.find((projection) => projection.settings.scenario_key === 'expected');
  const pointByDate = new Map(expected?.annual_points.map((point) => [point.on, point]) ?? []);
  const eventRows = rows.filter((row) => row.events.length);
  return <Box component="section" aria-labelledby="family-runway-title" sx={{ bgcolor: '#fff', border: '1px solid #DCE7F2', borderRadius: 3, p: { xs: 2, md: 3 }, minWidth: 0 }}>
    <Typography id="family-runway-title" variant="h6" sx={{ color: '#102A43', fontWeight: 800 }}>Family wealth runway</Typography>
    <Typography variant="body2" sx={{ color: '#52677C', mb: 1 }}>Expected wealth composition, with conservative and optimistic boundaries and funded family milestones.</Typography>
    <Stack direction="row" useFlexGap flexWrap="wrap" spacing={1} aria-label="Chart legend" sx={{ mb: 1 }}>
      {[['Total net worth', RUNWAY_LINE_COLORS.total], ['Financial assets', RUNWAY_LINE_COLORS.financial], ['Property value', RUNWAY_LINE_COLORS.property], ['Conservative total', RUNWAY_LINE_COLORS.conservative], ['Optimistic total', RUNWAY_LINE_COLORS.optimistic]].map(([label, color]) => <Chip key={label} size="small" label={label} sx={{ '&::before': { content: '""', width: 14, borderTop: `2px solid ${color}`, mr: .75 } }} />)}
    </Stack>
    <Box role="img" aria-label="Family wealth runway line chart. Expected total net worth is split into financial assets and property value; milestone rails identify planned family events." sx={{ height: { xs: 320, md: 390 }, width: '100%', minWidth: 0 }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows} margin={{ top: 35, right: 18, bottom: 8, left: 8 }}>
          <CartesianGrid vertical={false} stroke="#E3EBF3" strokeDasharray="3 4" />
          <XAxis dataKey="on" tickFormatter={(on) => String(on).slice(0, 4)} tick={{ fill: '#52677C', fontSize: 11 }} />
          <YAxis width={66} tickFormatter={(value) => formatCrore(Number(value))} tick={{ fill: '#52677C', fontSize: 10 }} />
          <Tooltip content={<RunwayTooltipContent pointByDate={pointByDate} />} />
          {eventRows.map((row) => <ReferenceLine key={row.on} x={row.on} stroke={row.events.some((event) => event.funding_treatment === 'asset_conversion') ? '#0F9D8A' : '#7357B6'} strokeDasharray="4 4" label={{ value: aggregateRunwayEvents(row.events)[0]?.label, position: 'top', fill: '#102A43', fontSize: 10 }} />)}
          <Line type="monotone" dataKey="conservative_total_inr" name="Conservative total" stroke={RUNWAY_LINE_COLORS.conservative} strokeWidth={1.5} strokeDasharray="5 5" dot={false} connectNulls isAnimationActive={RUNWAY_LINE_ANIMATION_ACTIVE} />
          <Line type="monotone" dataKey="optimistic_total_inr" name="Optimistic total" stroke={RUNWAY_LINE_COLORS.optimistic} strokeWidth={1.5} strokeDasharray="5 5" dot={false} connectNulls isAnimationActive={RUNWAY_LINE_ANIMATION_ACTIVE} />
          <Line type="monotone" dataKey="expected_total_inr" name="Total net worth" stroke={RUNWAY_LINE_COLORS.total} strokeWidth={3.5} dot={false} connectNulls isAnimationActive={RUNWAY_LINE_ANIMATION_ACTIVE} />
          <Line type="monotone" dataKey="expected_financial_assets_inr" name="Financial assets" stroke={RUNWAY_LINE_COLORS.financial} strokeWidth={2.5} dot={false} connectNulls isAnimationActive={RUNWAY_LINE_ANIMATION_ACTIVE} />
          <Line type="monotone" dataKey="expected_property_value_inr" name="Property value" stroke={RUNWAY_LINE_COLORS.property} strokeWidth={2.5} dot={false} connectNulls isAnimationActive={RUNWAY_LINE_ANIMATION_ACTIVE} />
        </LineChart>
      </ResponsiveContainer>
    </Box>
    <Box sx={{ position: 'absolute', width: 1, height: 1, p: 0, m: -1, overflow: 'hidden', clip: 'rect(0 0 0 0)', whiteSpace: 'nowrap', border: 0 }}>
      <table><caption>Annual family wealth data</caption><thead><tr><th>Date</th><th>Expected financial assets</th><th>Expected property value</th><th>Expected total</th><th>Conservative total</th><th>Optimistic total</th><th>Events</th></tr></thead><tbody>
        {rows.map((row) => <tr key={row.on}><th>{row.on}</th><td>{formatCrore(row.expected_financial_assets_inr)}</td><td>{formatCrore(row.expected_property_value_inr)}</td><td>{formatCrore(row.expected_total_inr)}</td><td>{formatCrore(row.conservative_total_inr)}</td><td>{formatCrore(row.optimistic_total_inr)}</td><td>{row.events.length ? row.events.map((event) => `${event.goal_name} ${formatCrore(event.amount_inr)}`).join('; ') : 'None'}</td></tr>)}
      </tbody></table>
    </Box>
    <Box component="ul" aria-label="Family wealth runway events" sx={{ m: 0, mt: 1, pl: 2.5 }}>
      {eventRows.map((row) => <li key={row.on}><Typography variant="body2" component="span" fontWeight={700}>{row.year} milestones: </Typography>{row.events.map((event: FamilyRunwayEvent) => <Typography component="span" variant="body2" key={event.goal_key}>{event.goal_name} ({event.funding_treatment === 'asset_conversion' ? 'Transfer to property' : `${formatCrore(event.amount_inr)} outflow`}; {event.shortfall_inr > 0 ? `${formatCrore(event.shortfall_inr)} shortfall` : 'funded'}){event !== row.events.at(-1) ? '; ' : ''}</Typography>)}</li>)}
    </Box>
  </Box>;
};

export default FamilyWealthRunwayChart;
