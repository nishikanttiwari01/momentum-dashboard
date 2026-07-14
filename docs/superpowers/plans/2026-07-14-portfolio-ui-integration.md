# Portfolio UI Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the real Portfolio page using the approved compact dashboard design while preserving all existing behavior and API integrations.

**Architecture:** Keep `Portfolio.tsx` as the data and interaction owner. Add focused presentational components for the allocation donut, dashboard overview, and simulated Excel-preview control; pass existing API results into them without changing backend contracts or transaction/chart components.

**Tech Stack:** React 18, TypeScript, Material UI, Recharts, Vitest, React DOM server rendering

---

### Task 1: Allocation and overview presentation

**Files:**
- Create: `frontend/src/features/portfolio/PortfolioAllocation.tsx`
- Create: `frontend/src/features/portfolio/PortfolioAllocation.test.tsx`
- Modify: `frontend/src/pages/Portfolio.tsx`

- [ ] Write a failing render test asserting category labels, percentages, amounts, and an accessible allocation chart.
- [ ] Run `npm test -- --run src/features/portfolio/PortfolioAllocation.test.tsx` and verify failure because the component is absent.
- [ ] Implement a responsive Recharts donut with a compact legend and an overview section that consumes existing summary/allocation values.
- [ ] Replace the allocation chips and summary strip in `Portfolio.tsx` with the new presentation while retaining `forceRefresh` and all existing values.
- [ ] Re-run the focused test and verify it passes.

### Task 2: UI-only Excel refresh preview

**Files:**
- Create: `frontend/src/features/portfolio/PortfolioWorkbookPreview.tsx`
- Create: `frontend/src/features/portfolio/PortfolioWorkbookPreview.test.tsx`
- Modify: `frontend/src/pages/Portfolio.tsx`

- [ ] Write a failing render test asserting `.xlsx` acceptance, the seven approved sheet names, privacy text, and explicit preview-only behavior.
- [ ] Run `npm test -- --run src/features/portfolio/PortfolioWorkbookPreview.test.tsx` and verify failure because the component is absent.
- [ ] Implement a local filename-only preview with no upload request, persistence, or parsing.
- [ ] Add it below the existing portfolio sections without changing any existing query, mutation, dialog, fund chart, or transaction behavior.
- [ ] Re-run the focused test and verify it passes.

### Task 3: Regression and browser validation

**Files:**
- Verify: `frontend/src/pages/Portfolio.tsx`
- Verify: `frontend/src/features/portfolio/UsInvestmentsSection.tsx`
- Verify: `frontend/src/features/portfolio/AddFundTransactionDialog.tsx`

- [ ] Run the portfolio feature tests and production build.
- [ ] Render `/portfolio` in Edge and verify the donut, compact overview, existing fund table, expandable NAV chart, transaction actions, QQQ section, and workbook preview appear together.
- [ ] Click a fund, select 5Y, and verify the full NAV history still renders with purchase markers.
- [ ] Open an existing add-transaction dialog and verify it remains functional.
- [ ] Select `investment.xlsx` and verify the preview changes locally without a network request.
- [ ] Commit only the integration files after all checks pass.
