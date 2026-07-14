# Vibrant Mutual-Fund NAV Chart Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade expanded Indian mutual-fund NAV charts with a gradient area, meaningful zones, vivid markers and stronger metric badges without changing chart data or controls.

**Architecture:** Keep all fetching, filtering and transaction behavior in `FundNavChart`. Add presentation-only Recharts definitions and MUI styling, protected by a source-level regression test and the existing chart-data tests.

**Tech Stack:** React, TypeScript, Material UI, Recharts, Vitest, Vite.

---

### Task 1: Chart Visual Regression

**Files:**
- Create: `frontend/src/features/portfolio/FundNavChartStyle.test.ts`
- Modify: `frontend/src/pages/Portfolio.tsx`

- [ ] Write a source regression test requiring `Area`, `navAreaGradient`, `data-testid="fund-nav-chart"`, the average reference line, and latest NAV badge.
- [ ] Run `npm test -- --run src/features/portfolio/FundNavChartStyle.test.ts`; expect failure because the area treatment is absent.
- [ ] Import Recharts `Area`, add a stable per-fund gradient, render the NAV area and line, style the chart surface, strengthen grid/axis colors, and add latest/average badges.
- [ ] Style purchase dots with amber fill, white border and glow while preserving transaction tooltip behavior.
- [ ] Rerun the focused test and existing `fundChartData.test.ts`; expect all tests to pass.

### Task 2: Verification

**Files:**
- Verify: `frontend/src/pages/Portfolio.tsx`
- Verify: `frontend/src/features/portfolio/FundNavChartStyle.test.ts`

- [ ] Run `npm test -- --run`; expect zero failures.
- [ ] Run `npm run build`; expect a successful Vite build.
- [ ] Render `/portfolio`, expand a mutual fund and inspect 1Y and 5Y chart ranges.
- [ ] Confirm the gradient is complete, purchase dots remain visible, labels are readable and the chart is not clipped.
- [ ] Commit only the NAV-chart implementation, test and plan.
