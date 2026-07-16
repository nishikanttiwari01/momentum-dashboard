import React, { useMemo, useState } from "react";
import {
  Box,
  Button,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { familyRunwayRows, formatCrore } from "./familyWealthMath";
import type {
  AnnualRunwayEvent,
  AnnualRunwayPoint,
  FamilyScenarioKey,
  FamilyScenarioProjection,
} from "./wealthTypes";
export const RUNWAY_LINE_COLORS = {
  total: "#102A43",
  financial: "#2563EB",
  property: "#0F9D8A",
  conservative: "#D98A00",
  expected: "#2563EB",
  optimistic: "#7357B6",
} as const;
export const RUNWAY_LINE_ANIMATION_ACTIVE = false;
export function aggregateRunwayEvents(events: readonly AnnualRunwayEvent[]) {
  return events.length
    ? [
        {
          label:
            events.length === 1
              ? events[0].goal_name
              : `${events.length} milestones`,
          events: [...events],
        },
      ]
    : [];
}
export function runwayTooltipLines(p: AnnualRunwayPoint) {
  return [
    `Total net worth ${formatCrore(p.total_net_worth_inr)}`,
    `Financial assets ${formatCrore(p.financial_assets_inr)}`,
    `Property value ${formatCrore(p.property_value_inr)}`,
    `Annual contributions ${formatCrore(p.annual_contributions_inr)}`,
    `Rent ${formatCrore(p.annual_rent_inr)}`,
    `Rent received ${formatCrore(p.rent_received_inr)}`,
    `Rent reinvested ${formatCrore(p.rent_reinvested_inr)}`,
    `Financial growth ${formatCrore(p.financial_growth_inr)}`,
    `Property growth ${formatCrore(p.property_growth_inr)}`,
    `Goal outflows ${formatCrore(p.goal_outflows_inr)}`,
    ...p.events.map(
      (e) =>
        `${e.goal_name}: funded ${formatCrore(e.funded_amount_inr)}${e.shortfall_inr ? `; shortfall ${formatCrore(e.shortfall_inr)}` : ""}`,
    ),
  ];
}
export const RunwayTooltipContent = ({
  active,
  label,
  points,
  pointByDate,
}: {
  active?: boolean;
  label?: string;
  points?: Map<string, AnnualRunwayPoint>;
  pointByDate?: Map<string, AnnualRunwayPoint>;
}) => {
  const p = label ? (points ?? pointByDate)?.get(label) : undefined;
  return active && p ? (
    <Box
      sx={{
        bgcolor: "#fff",
        border: "1px solid #D9E5F2",
        borderRadius: 2,
        p: 1.5,
        boxShadow: 3,
      }}
    >
      <Typography fontWeight={900}>
        {p.on} · age {p.age ?? "—"}
      </Typography>
      {runwayTooltipLines(p).map((x) => (
        <Typography key={x} variant="caption" display="block">
          {x}
        </Typography>
      ))}
    </Box>
  ) : null;
};
export const FamilyWealthRunwayChart: React.FC<{
  projections: readonly FamilyScenarioProjection[];
}> = ({ projections }) => {
  const [mode, setMode] = useState<"composition" | "compare">("composition");
  const [selected, setSelected] = useState<FamilyScenarioKey>("expected");
  const rows = familyRunwayRows(projections);
  const projection =
    projections.find((p) => p.settings.scenario_key === selected) ??
    projections[0];
  const points = useMemo(
    () => new Map(projection?.annual_points.map((p) => [p.on, p]) ?? []),
    [projection],
  );
  const events = projection?.annual_points.filter((p) => p.events.length) ?? [];
  const milestone = projection?.december_2029_milestone;
  return (
    <Box
      component="section"
      aria-labelledby="family-runway-title"
      sx={{ minWidth: 0 }}
    >
      <Stack
        direction={{ xs: "column", sm: "row" }}
        justifyContent="space-between"
        gap={1}
      >
        <Box>
          <Typography id="family-runway-title" variant="h6" fontWeight={900}>
            Family wealth runway
          </Typography>
          <Typography color="text.secondary">
            Combined financial and property wealth through age 80.
          </Typography>
        </Box>
        <Stack direction="row" gap={1}>
          <Button
            variant={mode === "composition" ? "contained" : "outlined"}
            onClick={() => setMode("composition")}
          >
            Composition
          </Button>
          <Button
            variant={mode === "compare" ? "contained" : "outlined"}
            onClick={() => setMode("compare")}
          >
            Compare scenarios
          </Button>
          {mode === "composition" && (
            <TextField
              select
              size="small"
              label="Scenario"
              value={selected}
              onChange={(e) => setSelected(e.target.value as FamilyScenarioKey)}
            >
              {projections.map((p) => (
                <MenuItem
                  key={p.settings.scenario_key}
                  value={p.settings.scenario_key}
                >
                  {p.settings.scenario_key}
                </MenuItem>
              ))}
            </TextField>
          )}
        </Stack>
      </Stack>
      <Box
        role="img"
        aria-label={`${mode} lifetime wealth chart through age 80`}
        sx={{ height: { xs: 350, md: 430 }, width: "100%", minWidth: 0 }}
      >
        <ResponsiveContainer>
          <LineChart
            data={rows}
            margin={{ top: 38, right: 20, bottom: 8, left: 8 }}
          >
            <CartesianGrid
              vertical={false}
              stroke="#E3EBF3"
              strokeDasharray="3 4"
            />
            <XAxis dataKey="on" tickFormatter={(x) => String(x).slice(0, 4)} />
            <YAxis width={66} tickFormatter={(v) => formatCrore(Number(v))} />
            <Tooltip content={<RunwayTooltipContent points={points} />} />
            <ReferenceLine
              x="2029-12-31"
              stroke="#E11D48"
              strokeWidth={2}
              label={{
                value: `₹15 Cr · Dec 2029 ${milestone?.on_track ? "✓" : "gap"}`,
                position: "top",
                fill: "#BE123C",
              }}
            />
            {events.map((p) => (
              <ReferenceLine
                key={p.on}
                x={p.on}
                stroke="#7357B6"
                strokeDasharray="4 4"
                label={{
                  value: aggregateRunwayEvents(p.events)[0]?.label,
                  position: "top",
                  fontSize: 10,
                }}
              />
            ))}
            {mode === "compare" ? (
              projections.map((p) => (
                <Line
                  key={p.settings.scenario_key}
                  dataKey={`${p.settings.scenario_key}_total_inr`}
                  stroke={RUNWAY_LINE_COLORS[p.settings.scenario_key]}
                  strokeWidth={p.settings.scenario_key === "expected" ? 3 : 2}
                  dot={false}
                  isAnimationActive={false}
                />
              ))
            ) : (
              <>
                <Line
                  dataKey={`${selected}_total_inr`}
                  stroke={RUNWAY_LINE_COLORS.total}
                  strokeWidth={3}
                  dot={false}
                  isAnimationActive={false}
                />
                <Line
                  dataKey={`${selected}_financial_assets_inr`}
                  stroke={RUNWAY_LINE_COLORS.financial}
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                />
                <Line
                  dataKey={`${selected}_property_value_inr`}
                  stroke={RUNWAY_LINE_COLORS.property}
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                />
              </>
            )}
          </LineChart>
        </ResponsiveContainer>
      </Box>
      <Box
        sx={{
          position: "absolute",
          width: 1,
          height: 1,
          overflow: "hidden",
          clip: "rect(0 0 0 0)",
        }}
      >
        <table>
          <caption>Annual family wealth data</caption>
          <thead>
            <tr>
              <th>Date and age</th>
              <th>Selected total</th>
              <th>Financial</th>
              <th>Property</th>
              <th>Rent received</th>
              <th>Rent reinvested</th>
              <th>Conservative total</th><th>Expected total</th><th>Optimistic total</th><th>Events</th>
            </tr>
          </thead>
          <tbody>
            {projection?.annual_points.map((p) => (
              <tr key={p.on}>
                <th>
                  {p.on} age {p.age}
                </th>
                <td>{formatCrore(p.total_net_worth_inr)}</td>
                <td>{formatCrore(p.financial_assets_inr)}</td>
                <td>{formatCrore(p.property_value_inr)}</td>
                <td>{formatCrore(p.rent_received_inr)}</td>
                <td>{formatCrore(p.rent_reinvested_inr)}</td>
                <td>{formatCrore(rows.find((r) => r.on === p.on)?.conservative_total_inr)}</td>
                <td>{formatCrore(rows.find((r) => r.on === p.on)?.expected_total_inr)}</td>
                <td>{formatCrore(rows.find((r) => r.on === p.on)?.optimistic_total_inr)}</td>
                <td>{p.events.map((event) => `${event.goal_name} ${formatCrore(event.amount_inr)}`).join('; ')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Box>
      <Box component="ul">
        {events.flatMap((p) => [<Typography component="span" key={`${p.on}-heading`} fontWeight={800}>{p.on.slice(0, 4)} milestones</Typography>, ...p.events.map((e) => (
            <li key={`${p.on}-${e.goal_key}`}>
              {p.on.slice(0, 4)} · {e.goal_name}:{" "}
              {e.funding_treatment === "asset_conversion"
                ? "Transfer to property from financial assets"
                : `${formatCrore(e.funded_amount_inr)} paid from financial assets only`}
              {e.shortfall_inr
                ? ` · ${formatCrore(e.shortfall_inr)} shortfall`
                : ""}
            </li>
          ))])}
      </Box>
    </Box>
  );
};
export default FamilyWealthRunwayChart;
