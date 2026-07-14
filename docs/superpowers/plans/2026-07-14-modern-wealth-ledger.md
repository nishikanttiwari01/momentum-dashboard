# Modern Wealth Ledger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the complete Portfolio page as an icon-led Indian wealth dashboard with a labeled area-growth chart while preserving all portfolio behavior.

**Architecture:** Add small presentation components for section headings and metric tiles, then upgrade the workbook overview charts and asset rows. Apply shared visual treatment to existing Portfolio sections without changing API data, calculations, dialogs or event handlers.

**Tech Stack:** React 18, TypeScript, Material UI 6, MUI Icons, Recharts 3, Vitest, Vite.

---

## File Structure

- Create `frontend/src/features/portfolio/PortfolioVisuals.tsx`: reusable section header, icon tile, metric tile and asset-icon resolver.
- Create `frontend/src/features/portfolio/PortfolioVisuals.test.tsx`: semantic rendering tests for shared visuals.
- Modify `frontend/src/features/portfolio/PortfolioWorkbookSnapshot.tsx`: area chart, crore labels, icon-led asset rows and labeled balance bars.
- Modify `frontend/src/features/portfolio/PortfolioWorkbookSnapshot.test.tsx`: chart and icon acceptance tests.
- Modify `frontend/src/features/portfolio/PortfolioAllocation.tsx`: visual polish compatible with compact layout.
- Modify `frontend/src/pages/Portfolio.tsx`: metric tiles and consistent section-card styling while preserving handlers.

### Task 1: Shared Portfolio Visual Components

- [ ] Write `PortfolioVisuals.test.tsx` asserting that a section header renders its title and accessible icon context, metric tiles render label/value, and `assetIconFor('Mutual funds')` resolves to the mutual-fund icon.
- [ ] Run `npm test -- --run src/features/portfolio/PortfolioVisuals.test.tsx`; expect failure because the module does not exist.
- [ ] Implement `PortfolioSectionHeader`, `PortfolioMetricTile`, `PortfolioIconTile` and `assetIconFor` in `PortfolioVisuals.tsx` using MUI components and icons.
- [ ] Rerun the focused test; expect all assertions to pass.

### Task 2: Wealth Area Chart and Asset Icons

- [ ] Extend `PortfolioWorkbookSnapshot.test.tsx` to require `data-chart-type="wealth-area"`, direct labels `₹5.82 Cr`, `₹8.25 Cr`, `₹8.31 Cr`, and icon-labeled asset rows.
- [ ] Run the focused snapshot test; expect failure because the chart is still a line chart and rows have no icons.
- [ ] Replace the market `Line` with an `Area`, add a blue gradient, direct crore labels, a muted dashed principal line, icon-led headings and row icons.
- [ ] Add direct crore labels to balance-sheet bars and keep tooltips formatted in crores.
- [ ] Rerun snapshot and allocation tests; expect them to pass.

### Task 3: Complete Portfolio Page Styling

- [ ] Add a Portfolio page source regression test that requires shared metric tiles and stable test IDs for signals, funds and QQQ sections.
- [ ] Run the regression test; expect failure because the shared tiles and IDs are absent.
- [ ] Replace plain summary items with `PortfolioMetricTile` instances and apply the Modern Wealth Ledger card/header treatment to allocation, signals, funds and QQQ containers.
- [ ] Preserve all existing callbacks, dialogs, range controls, expansion state and transaction components unchanged.
- [ ] Run all frontend tests; expect zero failures.

### Task 4: Responsive and Browser Verification

- [ ] Run `npm run build`; expect Vite to finish successfully.
- [ ] Run `git diff --check`; expect no whitespace errors.
- [ ] Render `/portfolio` at 1720px width and verify the area fill, all three market labels, asset icons, balanced overview widths and complete donut.
- [ ] Render `/portfolio` at 390px width and verify stacked cards, no page-level horizontal overflow and usable action controls.
- [ ] Correct any visual defect with a failing regression test first, then rerun tests, build and both browser renders.
- [ ] Commit only the portfolio files and this plan, leaving unrelated working-tree changes untouched.
