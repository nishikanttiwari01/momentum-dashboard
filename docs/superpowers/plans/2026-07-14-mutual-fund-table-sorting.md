# Mutual-Fund Table Sorting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add stable, accessible client-side sorting to every meaningful data column in the Portfolio mutual-funds table.

**Architecture:** Add a focused pure sorting module that maps sort keys to raw fund values and always places missing values last. Keep sort state and Material UI header controls in `Portfolio.tsx`, derive a sorted copy of the existing funds array, and preserve expanded-chart identity through the existing fund ID.

**Tech Stack:** React, TypeScript, Material UI, Vitest, Vite

---

## File Structure

- Create `frontend/src/features/portfolio/fundTableSort.ts`: sort types, raw-value selection and stable comparison.
- Create `frontend/src/features/portfolio/fundTableSort.test.ts`: sorting behavior tests.
- Create `frontend/src/features/portfolio/FundTableSortingStyle.test.ts`: sortable-header integration contract.
- Modify `frontend/src/pages/Portfolio.tsx`: sort state, derived order and accessible `TableSortLabel` headers.

### Task 1: Build the pure sorting helper

**Files:**
- Create: `frontend/src/features/portfolio/fundTableSort.ts`
- Create: `frontend/src/features/portfolio/fundTableSort.test.ts`

- [ ] **Step 1: Write failing helper tests**

Define representative funds and assert that `sortFunds` preserves input order when the key is `null`, sorts Fund text case-insensitively, sorts Invested ascending and descending, keeps missing XIRR values last in both directions, and preserves original order for equal values.

```ts
expect(sortFunds(funds, null, 'asc')).toEqual(funds);
expect(sortFunds(funds, 'fund', 'asc').map((fund) => fund.name)).toEqual(['alpha', 'Beta', 'Zulu']);
expect(sortFunds(funds, 'invested', 'desc').map((fund) => fund.id)).toEqual(['high', 'low', 'missing']);
expect(sortFunds(funds, 'xirr', 'desc').at(-1)?.id).toBe('missing');
```

- [ ] **Step 2: Run the helper test and verify it fails**

Run: `npm test -- --run src/features/portfolio/fundTableSort.test.ts`

Expected: FAIL because `fundTableSort` does not exist.

- [ ] **Step 3: Implement sort keys, value extraction and stable comparison**

Export `FundSortKey`, `SortDirection`, `FundSortRecord` and `sortFunds`. Support `fund`, `category`, `nav`, `return1m`, `return6m`, `return1y`, `drawdown`, `invested`, `value`, `xirr`, `averageNav` and `gain`. Decorate each record with its input index, compare populated values, use `localeCompare` for text, reverse only populated comparisons for descending order, and use the input index for ties. Return a new array.

- [ ] **Step 4: Run the helper test and verify it passes**

Run: `npm test -- --run src/features/portfolio/fundTableSort.test.ts`

Expected: all helper tests pass.

- [ ] **Step 5: Commit the helper**

```bash
git add frontend/src/features/portfolio/fundTableSort.ts frontend/src/features/portfolio/fundTableSort.test.ts
git commit -m "feat: add mutual fund table sorting helper"
```

### Task 2: Add sortable headers and state

**Files:**
- Create: `frontend/src/features/portfolio/FundTableSortingStyle.test.ts`
- Modify: `frontend/src/pages/Portfolio.tsx`

- [ ] **Step 1: Write the failing integration contract**

Read `Portfolio.tsx` and assert it imports `TableSortLabel` and `sortFunds`, renders sortable header labels for Fund and XIRR, derives `sortedFunds`, maps `sortedFunds`, and leaves Action and Links as plain table cells.

- [ ] **Step 2: Run the integration test and verify it fails**

Run: `npm test -- --run src/features/portfolio/FundTableSortingStyle.test.ts`

Expected: FAIL because the existing headers are static and the table maps `funds`.

- [ ] **Step 3: Add sorting state and interaction**

Add nullable `sortKey` and `sortDirection` state. Implement `handleSort(key)` so the active key toggles direction and a new key starts ascending. Derive `sortedFunds` with `React.useMemo(() => sortFunds(funds, sortKey, sortDirection), [funds, sortKey, sortDirection])`.

- [ ] **Step 4: Render accessible sortable headers**

Create a local header descriptor list for the 12 sortable columns. Wrap each label with `TableSortLabel`, set `active`, `direction`, and `onClick`, and set `TableCell sortDirection` only for the active key. Keep Action and Links unchanged. Render rows from `sortedFunds.map`.

- [ ] **Step 5: Run integration and portfolio tests**

Run: `npm test -- --run src/features/portfolio/FundTableSortingStyle.test.ts src/features/portfolio`

Expected: all tests pass.

- [ ] **Step 6: Commit the table integration**

```bash
git add frontend/src/pages/Portfolio.tsx frontend/src/features/portfolio/FundTableSortingStyle.test.ts
git commit -m "feat: add sorting to mutual fund table"
```

### Task 3: Verify production behavior

**Files:**
- Verify: `frontend/src/pages/Portfolio.tsx`
- Verify: `frontend/src/features/portfolio/fundTableSort.ts`

- [ ] **Step 1: Run the complete frontend test suite**

Run: `npm test -- --run`

Expected: all frontend tests pass.

- [ ] **Step 2: Run the production build**

Run: `npm run build`

Expected: Vite completes successfully.

- [ ] **Step 3: Validate the rendered table in a browser**

Open Portfolio and verify Fund sorts A–Z then Z–A, Invested sorts numerically, and XIRR keeps missing values last in both directions. Confirm the active arrow changes direction.

- [ ] **Step 4: Validate expanded-row behavior**

Expand a fund chart, sort by another column, and confirm the expanded NAV chart moves with and remains directly below the same fund.
