# Move Wealth Growth to Overview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Relocate the existing workbook wealth-growth chart from Investments to Overview and delete the Overview dummy chart.

**Architecture:** Reuse the exported `PortfolioWealthGrowth` component without changing its data or presentation. `PortfolioOverview` owns its placement; `Portfolio.tsx` stops rendering it.

**Tech Stack:** React, TypeScript, Material UI, Recharts, Vitest

---

### Task 1: Specify the new placement

**Files:**
- Modify: `frontend/src/features/portfolio/PortfolioHub.test.tsx`

- [ ] Render tab 0 and assert it includes `data-testid="portfolio-wealth-growth"`.
- [ ] Run `npm test -- --run src/features/portfolio/PortfolioHub.test.tsx` and confirm the assertion fails.

### Task 2: Move the chart

**Files:**
- Modify: `frontend/src/features/portfolio/PortfolioOverview.tsx`
- Modify: `frontend/src/pages/Portfolio.tsx`

- [ ] Delete the local `wealthHistory` dataset and dummy Recharts area-chart markup from Overview.
- [ ] Import and render `PortfolioWealthGrowth` in the same Overview grid position.
- [ ] Remove the `PortfolioWealthGrowth` import and render call from Investments.
- [ ] Simplify the remaining Investments allocation container so it uses the available width.

### Task 3: Verify and commit

**Files:**
- Test: `frontend/src/features/portfolio/PortfolioHub.test.tsx`

- [ ] Run the focused PortfolioHub test.
- [ ] Run `npm run build`.
- [ ] Commit only the plan, test, Overview, and Portfolio page changes.
