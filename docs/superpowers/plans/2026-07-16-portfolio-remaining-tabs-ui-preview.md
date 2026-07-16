# Portfolio Remaining Tabs UI Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the three inactive portfolio tabs with a compact, responsive mock-data UI for visual approval without changing backend or existing working tabs.

**Architecture:** Add one self-contained React component per preview tab and route them through `PortfolioHub`. Each component owns a small typed mock dataset and uses the existing MUI/Recharts stack; a shared preview badge makes the temporary data unmistakable.

**Tech Stack:** React, TypeScript, Material UI, Recharts, Vitest server rendering

---

### Task 1: Lock tab routing with a focused failing test

**Files:**
- Modify: `frontend/src/features/portfolio/PortfolioHub.test.tsx`

- [ ] Replace the placeholder-alert assertion with assertions that tabs 0, 1, and 3 return `PortfolioOverview`, `PortfolioAnnualReview`, and `PortfolioPropertiesRent`.
- [ ] Run `npm test -- --run src/features/portfolio/PortfolioHub.test.tsx` from `frontend` and confirm it fails because the components do not exist yet.

### Task 2: Build the Overview preview

**Files:**
- Create: `frontend/src/features/portfolio/PortfolioOverview.tsx`

- [ ] Add a compact preview badge and summary cards for net worth, invested capital, gains, and geographic exposure.
- [ ] Add allocation, three-year growth, India/US exposure, and insight sections using typed local sample data.
- [ ] Use responsive MUI grids and non-animated Recharts visuals with correct rupee/crore labels.

### Task 3: Build the Annual Review preview

**Files:**
- Create: `frontend/src/features/portfolio/PortfolioAnnualReview.tsx`

- [ ] Add local Jan–Dec annual records and a year selector.
- [ ] Show opening wealth, contributions, investment gains, property growth, closing wealth, and XIRR.
- [ ] Add the compact wealth bridge and year comparison table.

### Task 4: Build the Properties & Rent preview

**Files:**
- Create: `frontend/src/features/portfolio/PortfolioPropertiesRent.tsx`

- [ ] Add sample cards for Brigade land, Amrapali flat, and Gera office.
- [ ] Show principal, market value, appreciation, rent, occupancy, and rental yield.
- [ ] Add property value, rental income, and yield-comparison charts.

### Task 5: Activate the preview tabs

**Files:**
- Modify: `frontend/src/features/portfolio/PortfolioHub.tsx`

- [ ] Import and return the three preview components for tabs 0, 1, and 3.
- [ ] Preserve the current default Investments tab and existing Goals/Data Import routing exactly.

### Task 6: Verify the UI-only delivery

**Files:**
- Test: `frontend/src/features/portfolio/PortfolioHub.test.tsx`

- [ ] Run `npm test -- --run src/features/portfolio/PortfolioHub.test.tsx` and confirm it passes.
- [ ] Run `npm run build` and confirm TypeScript and Vite complete successfully.
- [ ] Review the diff to confirm no backend or existing investment/goal/import implementation was changed.
- [ ] Commit only the plan, three new components, hub routing, and focused test.
