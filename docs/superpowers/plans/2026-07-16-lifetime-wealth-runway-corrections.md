# Lifetime Wealth Runway Corrections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct household net worth, property and rent imports; project the family runway through age 80; and provide independently editable financial/property scenario assumptions with a December 2029 ₹15 Cr milestone.

**Architecture:** Extend workbook parsing with a reconciled household starting-state object, persist lifetime/scenario assumptions in a forward Alembic migration, and keep the projection engine as a pure function. The service layer composes imported data, overrides and projection output atomically. The frontend consumes the expanded contract, separates composition and comparison chart modes, and edits all three scenarios in a compact matrix.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2, Alembic, Pydantic 2, openpyxl, pytest, React 18, TypeScript, Material UI, Recharts, TanStack Query, Vitest.

---

## File responsibility map

- `backend/app/services/wealth_workbook.py`: parse and reconcile balance-sheet, fixed-asset and rent source values.
- `backend/app/services/wealth_import_service.py`: persist imported household totals/components without double-counting and preserve dated overrides.
- `backend/app/repos/models.py`: persisted lifetime-plan and scenario fields.
- `backend/alembic/versions/20260716_0010_lifetime_wealth_runway.py`: forward-compatible schema/default migration.
- `backend/app/schemas/wealth_portfolio.py`: strict request/response contracts and validation.
- `backend/app/services/family_wealth_projection.py`: pure age-80 projection, cash-only goal funding, property and rent rules.
- `backend/app/services/family_wealth_plan_service.py`: defaults, overrides, starting-state selection and atomic writes.
- `backend/app/api/v1/wealth_portfolio.py`: unchanged route shapes with expanded contracts and safe error mapping.
- `frontend/src/features/portfolio/wealthTypes.ts`: TypeScript mirror of backend contracts.
- `frontend/src/features/portfolio/familyWealthMath.ts`: chart rows, age labels and field-error mapping.
- `frontend/src/features/portfolio/FamilyWealthRunwayChart.tsx`: composition/compare chart modes and milestone rendering.
- `frontend/src/features/portfolio/FamilyScenarioMatrix.tsx`: compact three-scenario editor.
- `frontend/src/features/portfolio/FamilyPlanAssumptions.tsx`: rent, age and secondary assumptions.
- `frontend/src/features/portfolio/WealthGoalWorkspace.tsx`: query/mutation orchestration and ordered workspace.
- `frontend/src/features/portfolio/PortfolioSummaryHeader.tsx`: corrected combined totals and UTF-8 copy.

### Task 1: Parse and reconcile household wealth and rent

**Files:**
- Modify: `backend/app/services/wealth_workbook.py`
- Modify: `backend/app/services/wealth_import_service.py`
- Modify: `backend/tests/fixtures/wealth_workbook_factory.py`
- Test: `backend/tests/services/test_wealth_workbook.py`
- Test: `backend/tests/services/test_wealth_import_service.py`

- [ ] **Step 1: Add a failing workbook parser test**

Create a fixture containing latest balance-sheet values ₹4,46,58,852.25 financial, ₹3,84,00,000 fixed, ₹8,30,58,852.25 total and ₹5,86,63,055.25 principal; fixed-asset rows for Brigade, Amrapali and Gera; and rents ₹30,000 plus ₹14,000. Assert:

```python
assert parsed.household.financial_market_value_inr == 44_658_852.25
assert parsed.household.property_market_value_inr == 38_400_000
assert parsed.household.net_worth_market_value_inr == 83_058_852.25
assert parsed.household.invested_capital_inr == 58_663_055.25
assert parsed.household.monthly_rent_inr == 44_000
assert [asset.market_value_inr for asset in parsed.fixed_assets] == [21_600_000, 6_800_000, 10_000_000]
assert parsed.reconciliation_warnings == []
```

- [ ] **Step 2: Run the parser test and confirm the current omission**

Run: `pytest backend/tests/services/test_wealth_workbook.py -q`

Expected: FAIL because household fixed assets and rent are not represented in the parsed contract.

- [ ] **Step 3: Add focused parsed types and reconciliation**

Add immutable records equivalent to:

```python
@dataclass(frozen=True)
class ParsedHouseholdWealth:
    as_of: date
    financial_market_value_inr: Decimal
    property_market_value_inr: Decimal
    net_worth_market_value_inr: Decimal
    invested_capital_inr: Decimal
    monthly_rent_inr: Decimal

def reconcile_household(financial: Decimal, property_value: Decimal, total: Decimal) -> list[str]:
    delta = abs((financial + property_value) - total)
    return [] if delta <= Decimal("1") else [f"Household totals differ by ₹{delta:,.2f}"]
```

Select the rightmost populated `BALANCE SHEET` year, use `FIXED ASSET` only for component detail, and sum the two current rent rows. Do not add fixed components on top of the aggregate fixed total.

- [ ] **Step 4: Test import persistence and override preservation**

Assert a second workbook import refreshes workbook-sourced totals but leaves a later dated app override effective. Assert reconciliation warnings are persisted and missing rent/property produces a warning rather than zero.

Run: `pytest backend/tests/services/test_wealth_workbook.py backend/tests/services/test_wealth_import_service.py -q`

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```powershell
git add backend/app/services/wealth_workbook.py backend/app/services/wealth_import_service.py backend/tests/fixtures/wealth_workbook_factory.py backend/tests/services/test_wealth_workbook.py backend/tests/services/test_wealth_import_service.py
git commit -m "fix: import complete household wealth and rent"
```

### Task 2: Persist lifetime and per-scenario assumptions

**Files:**
- Create: `backend/alembic/versions/20260716_0010_lifetime_wealth_runway.py`
- Modify: `backend/app/repos/models.py`
- Test: `backend/tests/test_migrations.py`

- [ ] **Step 1: Write a failing migration test**

Upgrade a temporary database from `20260715_0009` to head and assert columns/defaults:

```python
assert plan.birth_year == 1984
assert plan.birth_month == 7
assert plan.projection_end_age == 80
assert scenarios["expected"].property_growth_pct == 6
assert scenarios["expected"].contribution_stop_age == 60
```

- [ ] **Step 2: Run the migration test**

Run: `pytest backend/tests/test_migrations.py -q`

Expected: FAIL because revision `0010` and the new fields do not exist.

- [ ] **Step 3: Add model fields and migration**

Add `birth_year`, `birth_month`, `projection_end_age` to `FamilyWealthPlan`. Add `property_growth_pct`, `monthly_contribution_inr`, `step_up_enabled`, `step_up_pct`, and `contribution_stop_age` to `FamilyWealthScenario`. Backfill the three existing rows with canonical defaults and retain existing financial return values.

The migration must be idempotent under normal Alembic execution and have a downgrade that removes only revision `0010` additions.

- [ ] **Step 4: Verify upgrade, downgrade and re-upgrade**

Run: `pytest backend/tests/test_migrations.py -q`

Expected: PASS, including `0009 -> 0010 -> 0009 -> 0010` coverage.

- [ ] **Step 5: Commit Task 2**

```powershell
git add backend/alembic/versions/20260716_0010_lifetime_wealth_runway.py backend/app/repos/models.py backend/tests/test_migrations.py
git commit -m "feat: persist lifetime runway assumptions"
```

### Task 3: Expand strict API contracts

**Files:**
- Modify: `backend/app/schemas/wealth_portfolio.py`
- Test: `backend/tests/api/test_family_wealth_plan_api.py`

- [ ] **Step 1: Write failing request/response contract tests**

Test a valid update containing:

```python
{
  "birth_year": 1984,
  "birth_month": 7,
  "projection_end_age": 80,
  "scenarios": [{
    "scenario_key": "expected",
    "financial_return_pct": 10,
    "property_growth_pct": 6,
    "monthly_contribution_inr": 600000,
    "step_up_enabled": True,
    "step_up_pct": 6,
    "contribution_stop_age": 60
  }]
}
```

Also assert field-addressable 422 errors for invalid birth month, end age before stop age, contribution stop age below current age, and out-of-range financial/property returns.

- [ ] **Step 2: Run focused API tests and observe failure**

Run: `pytest backend/tests/api/test_family_wealth_plan_api.py -q`

Expected: FAIL on missing fields or validation paths.

- [ ] **Step 3: Implement strict Pydantic contracts**

Use separate names `financial_return_pct` and `property_growth_pct`. Add annual-point fields `rent_received_inr`, `rent_reinvested_inr`, and `age`. Add milestone result fields `target_date`, `target_amount_inr`, `projected_value_inr`, `surplus_or_shortfall_inr`, and `on_track`.

- [ ] **Step 4: Verify contract tests**

Run: `pytest backend/tests/api/test_family_wealth_plan_api.py -q`

Expected: PASS with exact nested error locations such as `scenarios.1.property_growth_pct`.

- [ ] **Step 5: Commit Task 3**

```powershell
git add backend/app/schemas/wealth_portfolio.py backend/tests/api/test_family_wealth_plan_api.py
git commit -m "feat: define lifetime runway contracts"
```

### Task 4: Implement the pure lifetime projection rules

**Files:**
- Modify: `backend/app/services/family_wealth_projection.py`
- Test: `backend/tests/services/test_family_wealth_projection.py`

- [ ] **Step 1: Add failing projection tests**

Cover these invariants with exact balances:

```python
assert result.points[0].property_value_inr > 38_400_000
assert result.points[-1].age == 80
assert point_after_age_60.annual_contributions_inr == 0
assert point_2030.rent_received_inr > 0
assert point_2030.rent_reinvested_inr == 0
assert education_year.property_value_inr == property_before_growth
assert education_year.financial_assets_inr == max(0, financial_before_goal - funded_amount)
assert education_event.shortfall_inr == max(0, goal_cost - financial_before_goal)
```

Assert the Bangalore conversion subtracts only funded financial cash and adds exactly that funded amount to property. Assert the December 2029 milestone uses total net worth.

- [ ] **Step 2: Run the projection tests**

Run: `pytest backend/tests/services/test_family_wealth_projection.py -q`

Expected: FAIL on current zero starting property, truncated horizon, zero post-cutoff rent and shared-asset goal funding.

- [ ] **Step 3: Implement a year-by-year pure state transition**

Use an explicit state record:

```python
@dataclass(frozen=True)
class WealthState:
    financial_inr: Decimal
    property_inr: Decimal

funded = min(state.financial_inr, cash_goal_cost)
next_financial = state.financial_inr - funded
shortfall = cash_goal_cost - funded
```

Apply financial and property returns independently, stop contributions at the configured age, calculate rent received every year, and add only rent reinvested before the cutoff. Never deduct a cash goal from property. Continue points through the month the user reaches age 80.

- [ ] **Step 4: Verify pure projection tests**

Run: `pytest backend/tests/services/test_family_wealth_projection.py -q`

Expected: PASS for conservative, expected and optimistic scenarios and all invariant tests.

- [ ] **Step 5: Commit Task 4**

```powershell
git add backend/app/services/family_wealth_projection.py backend/tests/services/test_family_wealth_projection.py
git commit -m "fix: project complete lifetime wealth runway"
```

### Task 5: Compose starting data, overrides and atomic scenario saves

**Files:**
- Modify: `backend/app/services/family_wealth_plan_service.py`
- Modify: `backend/app/api/v1/wealth_portfolio.py`
- Test: `backend/tests/services/test_family_wealth_plan_service.py`
- Test: `backend/tests/api/test_family_wealth_plan_api.py`

- [ ] **Step 1: Write failing service tests**

Assert the service selects ₹4.47 Cr financial plus ₹3.84 Cr property, honors dated overrides, returns ₹8.31 Cr primary progress, exposes ₹44,000 starting rent, and does not commit a caller-owned transaction. Assert one invalid scenario rolls back the entire update.

- [ ] **Step 2: Run focused service/API tests**

Run: `pytest backend/tests/services/test_family_wealth_plan_service.py backend/tests/api/test_family_wealth_plan_api.py -q`

Expected: FAIL until orchestration uses the reconciled starting state and expanded scenario fields.

- [ ] **Step 3: Implement composition and restore defaults**

Map imported household totals to `starting_financial_inr` and `starting_property_inr`. Apply explicit dated overrides last. Seed July 1984, age 80, ₹44,000 rent, December 2029 target, and three scenario defaults. Restore defaults must reset every new field in one transaction.

- [ ] **Step 4: Verify service and API behavior**

Run: `pytest backend/tests/services/test_family_wealth_plan_service.py backend/tests/api/test_family_wealth_plan_api.py -q`

Expected: PASS, including missing-data warning, 409 projection conflict, 422 validation and safe 500 behavior.

- [ ] **Step 5: Commit Task 5**

```powershell
git add backend/app/services/family_wealth_plan_service.py backend/app/api/v1/wealth_portfolio.py backend/tests/services/test_family_wealth_plan_service.py backend/tests/api/test_family_wealth_plan_api.py
git commit -m "feat: serve corrected lifetime family plan"
```

### Task 6: Correct Portfolio encoding and summary values

**Files:**
- Modify: `frontend/src/features/portfolio/PortfolioSummaryHeader.tsx`
- Modify: affected files returned by the mojibake scan under `frontend/src/features/portfolio`
- Test: `frontend/src/features/portfolio/PortfolioSummaryHeader.test.tsx`
- Create: `frontend/src/features/portfolio/PortfolioEncoding.test.ts`

- [ ] **Step 1: Add a failing encoding regression test**

Read the Portfolio source tree and fail on known mojibake sequences:

```ts
for (const bad of ['â‚¹', 'Â·', 'â€', 'Ã']) expect(allPortfolioSource).not.toContain(bad);
```

Render the summary and assert `₹8.31 Cr`, `Combined household value · property included`, and invested capital `₹5.87 Cr` for the workbook fixture.

- [ ] **Step 2: Run the tests and confirm failure**

Run: `npm test -- --run src/features/portfolio/PortfolioEncoding.test.ts src/features/portfolio/PortfolioSummaryHeader.test.tsx`

Expected: FAIL on the current corrupted literals and incomplete totals.

- [ ] **Step 3: Replace corrupted literals and use formatters**

Remove hard-coded broken byte sequences. Use the established INR/crore formatter for currency and a valid UTF-8 middle dot for descriptive copy.

- [ ] **Step 4: Verify tests**

Run: `npm test -- --run src/features/portfolio/PortfolioEncoding.test.ts src/features/portfolio/PortfolioSummaryHeader.test.tsx`

Expected: PASS.

- [ ] **Step 5: Commit Task 6**

```powershell
git add frontend/src/features/portfolio
git commit -m "fix: render complete portfolio values in utf8"
```

### Task 7: Mirror contracts and build lifetime chart helpers

**Files:**
- Modify: `frontend/src/features/portfolio/wealthTypes.ts`
- Modify: `frontend/src/features/portfolio/wealthApi.ts`
- Modify: `frontend/src/features/portfolio/familyWealthMath.ts`
- Test: `frontend/src/features/portfolio/wealthApi.test.ts`
- Test: `frontend/src/features/portfolio/familyWealthMath.test.ts`

- [ ] **Step 1: Add failing TypeScript contract/helper tests**

Assert API payloads preserve all three scenarios and their independent fields. Assert chart rows run through 2064, include age, milestone facts, rent received/reinvested, and do not align scenario points by array index.

- [ ] **Step 2: Run focused tests**

Run: `npm test -- --run src/features/portfolio/wealthApi.test.ts src/features/portfolio/familyWealthMath.test.ts`

Expected: FAIL on the expanded backend response.

- [ ] **Step 3: Implement exact TypeScript mirrors and pure helpers**

Define `FamilyScenarioSettings` with financial/property returns, contribution, step-up and stop age. Extend annual rows with age and separate rent facts. Add a chart-mode type:

```ts
export type RunwayChartMode =
  | { kind: 'composition'; scenario: FamilyScenarioKey }
  | { kind: 'comparison' };
```

- [ ] **Step 4: Verify focused tests and type-check through build**

Run: `npm test -- --run src/features/portfolio/wealthApi.test.ts src/features/portfolio/familyWealthMath.test.ts && npm run build`

Expected: tests and build PASS.

- [ ] **Step 5: Commit Task 7**

```powershell
git add frontend/src/features/portfolio/wealthTypes.ts frontend/src/features/portfolio/wealthApi.ts frontend/src/features/portfolio/familyWealthMath.ts frontend/src/features/portfolio/wealthApi.test.ts frontend/src/features/portfolio/familyWealthMath.test.ts
git commit -m "feat: add lifetime runway frontend contracts"
```

### Task 8: Build chart modes and the compact scenario matrix

**Files:**
- Create: `frontend/src/features/portfolio/FamilyScenarioMatrix.tsx`
- Modify: `frontend/src/features/portfolio/FamilyWealthRunwayChart.tsx`
- Modify: `frontend/src/features/portfolio/FamilyPlanAssumptions.tsx`
- Test: `frontend/src/features/portfolio/WealthGoalWorkspace.test.tsx`

- [ ] **Step 1: Add failing render and interaction tests**

Test Composition mode renders only expected total/financial/property lines; Compare mode renders only three total lines. Test December 2029 marker prominence, age-80 endpoint, tooltip rent distinction, cash-goal event wording, inline matrix edits, dirty state, save payload and field errors.

- [ ] **Step 2: Run the focused UI test**

Run: `npm test -- --run src/features/portfolio/WealthGoalWorkspace.test.tsx`

Expected: FAIL because chart modes and `FamilyScenarioMatrix` do not exist.

- [ ] **Step 3: Implement line-only chart modes**

Add accessible segmented controls for Composition/Compare and scenario selection. Keep `Line`, not `Area`; no gradients. Use a bold target rail for December 2029 and lighter secondary goal rails. The tooltip must show calendar year, age, composition, contribution, both rent facts, both growth facts and goal events once.

- [ ] **Step 4: Implement the compact scenario matrix**

Use aligned rows and three responsive scenario columns. On narrow screens, preserve row labels and allow only the matrix container—not the page—to scroll horizontally. Expose one Save and recalculate action and label results as last saved while dirty.

- [ ] **Step 5: Verify focused tests and production build**

Run: `npm test -- --run src/features/portfolio/WealthGoalWorkspace.test.tsx && npm run build`

Expected: PASS with no TypeScript errors.

- [ ] **Step 6: Commit Task 8**

```powershell
git add frontend/src/features/portfolio/FamilyScenarioMatrix.tsx frontend/src/features/portfolio/FamilyWealthRunwayChart.tsx frontend/src/features/portfolio/FamilyPlanAssumptions.tsx frontend/src/features/portfolio/WealthGoalWorkspace.test.tsx
git commit -m "feat: add lifetime chart modes and scenario matrix"
```

### Task 9: Integrate the corrected workspace and verify end to end

**Files:**
- Modify: `frontend/src/features/portfolio/WealthGoalWorkspace.tsx`
- Modify: `frontend/src/features/portfolio/WealthGoalWorkspace.test.tsx`
- Modify: `frontend/src/features/portfolio/PortfolioWorkbookSnapshot.test.tsx`
- Test: backend and frontend suites listed below

- [ ] **Step 1: Add failing workspace acceptance tests**

Assert visible order: combined ₹15 Cr progress, lifetime chart, goal cards, passive-income panel, scenario matrix, assumptions. Assert import warnings, retry, restore, dirty preservation and existing Portfolio features remain reachable.

- [ ] **Step 2: Run workspace/portfolio tests**

Run: `npm test -- --run src/features/portfolio`

Expected: FAIL until the new data and components are wired into the workspace.

- [ ] **Step 3: Integrate query, draft reducer and mutations**

Keep accepted server data separate from the draft matrix. Save the primary goal, plan assumptions, scenarios and linked goals atomically through the family-plan endpoint. Preserve the last successful projection on save/recalculation failure and map server validation paths to matrix fields.

- [ ] **Step 4: Run all backend feature tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/services/test_wealth_workbook.py backend/tests/services/test_wealth_import_service.py backend/tests/services/test_family_wealth_projection.py backend/tests/services/test_family_wealth_plan_service.py backend/tests/api/test_family_wealth_plan_api.py backend/tests/test_migrations.py -q
```

Expected: PASS.

- [ ] **Step 5: Run the full frontend suite and build**

Run:

```powershell
cd frontend
npm test -- --run
npm run build
```

Expected: all tests PASS; build PASS. A pre-existing bundle-size warning is nonblocking.

- [ ] **Step 6: Validate a real workbook and browser rendering**

Use a temporary SQLite database, import `D:\WORK\NEW_STOCK_DASHBOARD\investment.xlsx`, and verify API values ₹4.47 Cr financial, ₹3.84 Cr property, ₹8.31 Cr total, ₹5.87 Cr invested capital and ₹44,000 rent. Render at approximately 1440×900 and 900×1200. Inspect both chart modes, December 2029 milestone, age-80 endpoint, post-2029 rent, scenario editing, no clipped rails/tooltips and no page-level horizontal overflow.

- [ ] **Step 7: Commit Task 9**

```powershell
git add frontend/src/features/portfolio/WealthGoalWorkspace.tsx frontend/src/features/portfolio/WealthGoalWorkspace.test.tsx frontend/src/features/portfolio/PortfolioWorkbookSnapshot.test.tsx
git commit -m "feat: integrate corrected lifetime wealth workspace"
```

### Task 10: Final regression and review gate

**Files:**
- No planned source changes; fix only verified blocking findings.

- [ ] **Step 1: Check repository hygiene**

Run: `git diff --check && git status --short`

Expected: no whitespace errors; unrelated user changes remain untouched; generated `package-lock.json` changes are not committed unless dependency declarations intentionally changed.

- [ ] **Step 2: Run final backend and frontend verification**

Run the full relevant backend suite, full frontend suite and production build from the merged candidate revision. Record exact pass counts.

- [ ] **Step 3: Review against the approved design**

Confirm every requirement in `docs/superpowers/specs/2026-07-16-lifetime-wealth-runway-corrections-design.md`, with particular attention to cash-only goal deductions, combined starting wealth, rent received after cutoff, scenario-specific property rates and age-80 rendering.

- [ ] **Step 4: Commit only if review fixes were required**

```powershell
git add backend/app/services/family_wealth_projection.py frontend/src/features/portfolio/FamilyWealthRunwayChart.tsx
git commit -m "fix: address lifetime runway review findings"
```

If the verified finding concerns different files, substitute only those explicitly reviewed paths; never stage the entire dirty worktree.
