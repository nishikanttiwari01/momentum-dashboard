import React from 'react';
import { Box, useMediaQuery } from '@mui/material';
import { CartesianGrid, LabelList, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { PrimaryGoalResponse } from './wealthTypes';
import { formatCompactCrore } from './wealthGoalMath';

export const GOAL_LINE_COLORS = { required: '#64748B', conservative: '#F59E0B', expected: '#2563EB', optimistic: '#059669' } as const;
export const endpointLabelText = (series: string, value: number) => `${series[0].toUpperCase() + series.slice(1)} ${formatCompactCrore(value)}`;

export const mergeGoalTrajectories = (data: PrimaryGoalResponse) => {
  const rows = new Map<string, Record<string, string | number>>();
  const add = (key: string, points: { on: string; balance_inr: number }[]) => points.forEach((point) => {
    const row = rows.get(point.on) ?? { on: point.on };
    row[key] = point.balance_inr;
    rows.set(point.on, row);
  });
  add('required', data.required_trajectory);
  data.scenario_projections.forEach((scenario) => add(scenario.settings.scenario_key, scenario.trajectory));
  return [...rows.values()].sort((a, b) => String(a.on).localeCompare(String(b.on)));
};

const EndpointLabel = ({ x, y, value, series }: { x?: number; y?: number; value?: number; series: string }) => value == null ? null : (
  <text x={x} y={y} dx={7} dy={4} fontSize={10} fontWeight={700} fill="currentColor" aria-label={endpointLabelText(series, value)}>{formatCompactCrore(value)}</text>
);

export const WealthGoalChart: React.FC<{ data: PrimaryGoalResponse }> = ({ data }) => {
  const rows = mergeGoalTrajectories(data);
  const reduced = useMediaQuery('(prefers-reduced-motion: reduce)');
  return <Box sx={{ height: { xs: 300, md: 350 }, width: '100%', minWidth: 0 }} role="img" aria-label="Required and scenario wealth trajectories" aria-description="Required path compared with conservative, expected, and optimistic projected wealth paths.">
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={rows} margin={{ top: 20, right: 70, bottom: 8, left: 8 }}>
        <CartesianGrid vertical={false} stroke="#E8EEF5" strokeDasharray="3 4" />
        <XAxis dataKey="on" tick={{ fontSize: 11 }} tickFormatter={(value) => String(value).slice(0, 7)} />
        <YAxis width={62} tick={{ fontSize: 10 }} tickFormatter={(value) => formatCompactCrore(Number(value))} />
        <Tooltip formatter={(value: number) => formatCompactCrore(value)} labelFormatter={(label) => `Date ${label}`} />
        {(Object.keys(GOAL_LINE_COLORS) as (keyof typeof GOAL_LINE_COLORS)[]).map((key) => <Line key={key} type="monotone" dataKey={key} name={key[0].toUpperCase() + key.slice(1)} stroke={GOAL_LINE_COLORS[key]} strokeWidth={key === 'required' ? 2 : 3} strokeDasharray={key === 'required' ? '6 5' : undefined} dot={false} connectNulls isAnimationActive={!reduced}>
          <LabelList dataKey={key} content={(props) => {
            const index = Number(props.index);
            return index === rows.length - 1 ? <EndpointLabel x={Number(props.x)} y={Number(props.y)} value={Number(props.value)} series={key} /> : null;
          }} />
        </Line>)}
      </LineChart>
    </ResponsiveContainer>
  </Box>;
};

export default WealthGoalChart;
