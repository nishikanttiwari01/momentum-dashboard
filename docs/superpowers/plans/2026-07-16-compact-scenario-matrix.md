# Compact Scenario Matrix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace oversized scenario fields with a compact responsive editor positioned immediately below the wealth chart.

**Architecture:** Keep the existing draft/update contract and change presentation only. `FamilyScenarioMatrix` renders a compact desktop matrix and stacked mobile cards; `WealthGoalWorkspace` controls placement. Existing mutation, validation and recalculation behavior remains unchanged.

**Tech Stack:** React 18, TypeScript, Material UI, Vitest.

---

### Task 1: Lock compact layout and placement with failing tests

**Files:**
- Modify: `frontend/src/features/portfolio/WealthGoalWorkspace.test.tsx`

- [ ] **Step 1: Add failing structure and style assertions**

Add tests that render `FamilyPlanWorkspaceView` and assert the scenario heading occurs after the chart controls and before goal-health content. Render `FamilyScenarioMatrix` and assert compact field markers, accessible labels, mobile-card marker, valid `₹`/`·` copy, and absence of `â‚¹`/`Â·`.

```tsx
expect(html.indexOf('Wealth composition')).toBeLessThan(html.indexOf('Scenario comparison'));
expect(html.indexOf('Scenario comparison')).toBeLessThan(html.indexOf('Goal readiness'));
expect(html).toContain('data-testid="compact-scenario-input"');
expect(html).not.toMatch(/â‚¹|Â·|Savingâ€¦/);
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `npm test -- --run src/features/portfolio/WealthGoalWorkspace.test.tsx`

Expected: FAIL because the matrix uses stretching text fields, has mojibake, and is placed below goal/passive sections.

- [ ] **Step 3: Commit the failing test only after confirming the expected failure**

Do not commit a red test separately; proceed directly to Task 2 and commit the green change atomically.

### Task 2: Implement compact responsive matrix and new placement

**Files:**
- Modify: `frontend/src/features/portfolio/FamilyScenarioMatrix.tsx`
- Modify: `frontend/src/features/portfolio/WealthGoalWorkspace.tsx`
- Modify: `frontend/src/features/portfolio/WealthGoalWorkspace.test.tsx`

- [ ] **Step 1: Replace stretching fields with compact controls**

Use `InputAdornment` and visually external row labels. Desktop controls use widths between 96 and 128 pixels, dense height, and no repeated floating label. Preserve accessible names:

```tsx
<TextField
  data-testid="compact-scenario-input"
  size="small"
  hiddenLabel
  inputProps={{ 'aria-label': `${scenarioLabel} ${rowLabel}` }}
  InputProps={{ endAdornment: <InputAdornment position="end">%</InputAdornment> }}
  sx={{ width: 108, '& .MuiInputBase-root': { height: 36 } }}
/>
```

Render step-up as a small switch and percentage control. Format monthly investment in lakh/month while converting back to INR for the unchanged draft payload.

- [ ] **Step 2: Add integrated scenario result footers**

Place ending net worth and December 2029 status under each scenario column in a lightly tinted block. Use correct UTF-8 copy: `Ending net worth · age 80`, `₹15 Cr · Dec 2029`, and `Saving…`.

- [ ] **Step 3: Add responsive mobile cards**

Use breakpoint display rules: desktop matrix at `md` and above; stacked compact scenario cards below `md`. Ensure the section uses `minWidth: 0`, `maxWidth: 100%`, and no page-level horizontal scrolling.

- [ ] **Step 4: Move scenario editor directly under the chart**

In `FamilyPlanWorkspaceView`, render `FamilyScenarioMatrix` immediately after `FamilyWealthRunwayChart` and before `FamilyGoalCards`/`PassiveIncomePanel`. Do not change API or draft behavior.

- [ ] **Step 5: Verify GREEN and regressions**

Run:

```powershell
npm test -- --run src/features/portfolio/WealthGoalWorkspace.test.tsx
npm test -- --run
npm run build
```

Expected: focused and full suites PASS; production build PASS; no React list-key warning from the scenario matrix.

- [ ] **Step 6: Commit**

```powershell
git add frontend/src/features/portfolio/FamilyScenarioMatrix.tsx frontend/src/features/portfolio/WealthGoalWorkspace.tsx frontend/src/features/portfolio/WealthGoalWorkspace.test.tsx
git commit -m "fix: compact scenario comparison controls"
```
