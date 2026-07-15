# Family Wealth Runway Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing ₹15 Cr goal simulator into a persisted family wealth runway that models linked goals, rent, contributions, property, passive income, and three scenarios from one combined portfolio.

**Architecture:** Preserve the existing primary-goal API for compatibility and add a consolidated family-plan read/write model. Keep projection math in a pure backend module, persistence orchestration in a service, and rendering transformations in focused frontend components. Derive projections on demand from the latest immutable portfolio snapshot and persisted plan settings.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, SQLite, pytest, React 18, TypeScript, Material UI, TanStack Query, Recharts, Vitest.

---

## File structure

### Backend

- Create `backend/alembic/versions/20260715_0009_family_wealth_plan.py`: tables and deterministic default seed.
- Modify `backend/app/repos/models.py`: persistence models for plan settings and linked goals.
- Modify `backend/app/schemas/wealth_portfolio.py`: request/response contracts and field validation.
- Create `backend/app/services/family_wealth_projection.py`: pure monthly projection and annual aggregation.
- Create `backend/app/services/family_wealth_plan_service.py`: persistence, portfolio starting values, atomic updates, and response assembly.
- Modify `backend/app/api/v1/wealth_portfolio.py`: family-plan GET, PUT, and restore-defaults routes.
- Create `backend/tests/services/test_family_wealth_projection.py`: calculation boundary tests.
- Create `backend/tests/services/test_family_wealth_plan_service.py`: persistence and workbook-refresh tests.
- Create `backend/tests/api/test_family_wealth_plan_api.py`: API contract, validation, and rollback tests.
- Modify `backend/tests/test_migrations.py`: migration/table/seed assertions.

### Frontend

- Modify `frontend/src/features/portfolio/wealthTypes.ts`: family-plan types.
- Modify `frontend/src/features/portfolio/wealthApi.ts`: family-plan API functions.
- Modify `frontend/src/features/portfolio/wealthApi.test.ts`: URL and payload tests.
- Create `frontend/src/features/portfolio/familyWealthMath.ts`: display and chart transformation helpers.
- Create `frontend/src/features/portfolio/familyWealthMath.test.ts`: transformation tests.
- Create `frontend/src/features/portfolio/FamilyWealthRunwayChart.tsx`: annual lines, event markers, and tooltip.
- Create `frontend/src/features/portfolio/FamilyGoalCards.tsx`: linked-goal status cards.
- Create `frontend/src/features/portfolio/PassiveIncomePanel.tsx`: 2029 feasibility panel.
- Create `frontend/src/features/portfolio/FamilyPlanAssumptions.tsx`: editable assumptions and linked goals.
- Modify `frontend/src/features/portfolio/WealthGoalWorkspace.tsx`: runway-first composition and save workflow.
- Modify `frontend/src/features/portfolio/WealthGoalWorkspace.test.tsx`: view states and interactions.

## Task 1: Persist the family plan and deterministic defaults

**Files:**
- Create: `backend/alembic/versions/20260715_0009_family_wealth_plan.py`
- Modify: `backend/app/repos/models.py`
- Modify: `backend/tests/test_migrations.py`

- [ ] **Step 1: Write the failing migration test**

Add assertions that an upgraded database contains `family_wealth_plans` and `family_wealth_goals`, one plan row, and six linked goals in deterministic display order:

```python
expected_tables |= {"family_wealth_plans", "family_wealth_goals"}
with engine.connect() as connection:
    plan = connection.execute(text(
        "select monthly_contribution_inr, contribution_step_up_enabled, "
        "contribution_step_up_pct, monthly_rent_inr, rent_growth_pct, "
        "property_growth_pct, withdrawal_rate_pct from family_wealth_plans"
    )).one()
    assert tuple(plan) == (600000.0, 0, 6.0, 45000.0, 6.0, 6.0, 3.5)
    keys = connection.execute(text(
        "select goal_key from family_wealth_goals order by display_order"
    )).scalars().all()
    assert keys == [
        "child_1_education", "passive_income", "bangalore_house",
        "child_2_education", "child_1_marriage", "child_2_marriage",
    ]
```

- [ ] **Step 2: Run the migration test and verify RED**

Run: `$env:PYTHONPATH='backend;.'; .\.venv\Scripts\python.exe -m pytest backend/tests/test_migrations.py -q`

Expected: FAIL because the two family-plan tables do not exist.

- [ ] **Step 3: Add SQLAlchemy models**

Add `FamilyWealthPlan` with one seeded row and these columns: `id`, `base_age`, `monthly_contribution_inr`, `contribution_step_up_enabled`, `contribution_step_up_pct`, `monthly_rent_inr`, `rent_growth_pct`, `reinvest_rent_until`, `property_growth_pct`, `withdrawal_rate_pct`, `amber_margin_pct`, `created_at`, and `updated_at`.

Add `FamilyWealthGoal` with `id`, `plan_id`, `goal_key`, `name`, `goal_type`, `current_value_amount_inr`, `target_date`, `inflation_pct`, `funding_treatment`, `priority`, `enabled`, and `display_order`. Enforce unique `(plan_id, goal_key)`.

```python
class FamilyWealthGoal(Base):
    __tablename__ = "family_wealth_goals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("family_wealth_plans.id"), index=True)
    goal_key: Mapped[str] = mapped_column(String(40))
    goal_type: Mapped[str] = mapped_column(String(24))
    current_value_amount_inr: Mapped[float] = mapped_column(Float)
    target_date: Mapped[date] = mapped_column(Date)
    inflation_pct: Mapped[float] = mapped_column(Float)
    funding_treatment: Mapped[str] = mapped_column(String(24))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    __table_args__ = (UniqueConstraint("plan_id", "goal_key"),)
```

- [ ] **Step 4: Create migration and seed explicit dates**

Use revision `20260715_0009` with `down_revision = "20260714_0008"`. Seed a base age of 42 and explicit dates derived from the approved 2026 plan base: education in 2032 and 2038, house in 2036, marriages in 2042 and 2044, and passive income on `2029-12-31`. Seed the passive-income current-value amount as `200000` monthly.

- [ ] **Step 5: Run migration tests and verify GREEN**

Run: `$env:PYTHONPATH='backend;.'; .\.venv\Scripts\python.exe -m pytest backend/tests/test_migrations.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add backend/alembic/versions/20260715_0009_family_wealth_plan.py backend/app/repos/models.py backend/tests/test_migrations.py
git commit -m "feat: persist family wealth plan defaults"
```

## Task 2: Define strict family-plan contracts

**Files:**
- Modify: `backend/app/schemas/wealth_portfolio.py`
- Create: `backend/tests/services/test_family_wealth_plan_service.py`

- [ ] **Step 1: Write failing schema tests**

Test ordered unique scenarios, supported goal treatments, positive withdrawal rate, safe numeric bounds, and duplicate goal-key rejection:

```python
def test_family_plan_rejects_duplicate_goal_keys(valid_family_plan_update):
    duplicate = valid_family_plan_update["goals"][0].copy()
    valid_family_plan_update["goals"].append(duplicate)
    with pytest.raises(ValidationError) as error:
        FamilyPlanUpdate.model_validate(valid_family_plan_update)
    assert error.value.errors()[0]["loc"] == ("goals",)

def test_family_plan_rejects_zero_withdrawal_rate(valid_family_plan_update):
    valid_family_plan_update["assumptions"]["withdrawal_rate_pct"] = 0
    with pytest.raises(ValidationError):
        FamilyPlanUpdate.model_validate(valid_family_plan_update)
```

- [ ] **Step 2: Run schema tests and verify RED**

Run: `$env:PYTHONPATH='backend;.'; .\.venv\Scripts\python.exe -m pytest backend/tests/services/test_family_wealth_plan_service.py -q`

Expected: FAIL because the family-plan schemas are undefined.

- [ ] **Step 3: Add request schemas**

Define:

```python
GoalType = Literal["education", "house", "marriage", "passive_income"]
FundingTreatment = Literal["expense", "asset_conversion", "income_target"]

class FamilyPlanAssumptions(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    monthly_contribution_inr: float = Field(ge=0, le=1_000_000_000_000)
    contribution_step_up_enabled: bool
    contribution_step_up_pct: float = Field(ge=0, le=25)
    monthly_rent_inr: float = Field(ge=0, le=1_000_000_000)
    rent_growth_pct: float = Field(ge=-25, le=50)
    reinvest_rent_until: date
    property_growth_pct: float = Field(ge=-25, le=50)
    withdrawal_rate_pct: float = Field(gt=0, le=20)
    amber_margin_pct: float = Field(ge=0, le=100)

class LinkedGoalSettings(BaseModel):
    goal_key: str = Field(pattern=r"^[a-z0-9_]+$", max_length=40)
    name: str = Field(min_length=1, max_length=120)
    goal_type: GoalType
    current_value_amount_inr: float = Field(gt=0, le=1_000_000_000_000_000)
    target_date: date
    inflation_pct: float = Field(ge=0, le=25)
    funding_treatment: FundingTreatment
    priority: int = Field(ge=1, le=100)
    enabled: bool
    display_order: int = Field(ge=0, le=100)
```

`FamilyPlanUpdate` contains `assumptions`, exactly three ordered scenario-return settings, and linked goals. Define a focused `FamilyScenarioSettings` contract containing only `scenario_key` and `annual_return_pct`; the single plan-level monthly contribution applies to all three scenarios. Its model validator rejects duplicate goal keys and treatment/type mismatches: house → asset conversion, passive income → income target, education/marriage → expense.

- [ ] **Step 4: Add response schemas**

Define `AnnualRunwayPoint`, `GoalHealth`, `PassiveIncomeAnalysis`, `FamilyScenarioSettings`, `FamilyScenarioProjection`, and `FamilyPlanResponse`. Include calculation date, snapshot ID, data health, assumptions, goals, scenarios, annual points, goal health, passive-income analysis, and the existing `PrimaryGoalResponse`.

- [ ] **Step 5: Run schema tests and verify GREEN**

Run the same pytest command. Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add backend/app/schemas/wealth_portfolio.py backend/tests/services/test_family_wealth_plan_service.py
git commit -m "feat: define family wealth plan contracts"
```

## Task 3: Build the pure monthly projection engine

**Files:**
- Create: `backend/app/services/family_wealth_projection.py`
- Create: `backend/tests/services/test_family_wealth_projection.py`

- [ ] **Step 1: Write failing tests for monthly contribution and step-up**

```python
def test_step_up_increases_contribution_each_january(base_input):
    result = project_family_wealth(replace(
        base_input,
        monthly_contribution=600_000,
        step_up_enabled=True,
        step_up_pct=6,
    ))
    assert result.monthly_points[0].contribution == 600_000
    january_2027 = next(p for p in result.monthly_points if p.on == date(2027, 1, 31))
    assert january_2027.contribution == 636_000
```

Add focused tests for flat contribution, rent growth/reinvestment, inflation, expense shortfalls, asset conversion, two same-month events, scenario separation, and a 600-month horizon rejection.

- [ ] **Step 2: Run projection tests and verify RED**

Run: `$env:PYTHONPATH='backend;.'; .\.venv\Scripts\python.exe -m pytest backend/tests/services/test_family_wealth_projection.py -q`

Expected: collection FAIL because `family_wealth_projection` does not exist.

- [ ] **Step 3: Implement immutable input/output types and rate conversion**

Use frozen dataclasses and Decimal for monetary state:

```python
MONEY = Decimal("0.01")

def monthly_rate(annual_pct: Decimal) -> Decimal:
    rate = (1.0 + float(annual_pct) / 100.0) ** (1.0 / 12.0) - 1.0
    if not math.isfinite(rate) or rate <= -1:
        raise UnsafeProjection("annual rate cannot produce a finite monthly rate")
    return Decimal(str(rate))
```

Define `ProjectionInput`, `ProjectionGoal`, `MonthlyRunwayPoint`, `ProjectedGoalResult`, and `ProjectionResult`. Do not import SQLAlchemy models into this module.

- [ ] **Step 4: Implement monthly event loop**

Implement opening balance → financial growth → contribution → reinvested rent → goal events → closing balance. For underfunded expenses, deduct only available financial assets, record unmet shortfall, and continue from zero. For asset conversion, move only the funded amount into future-house property and report any unfunded remainder.

- [ ] **Step 5: Implement annual aggregation and passive-income analysis**

Aggregate the last monthly point in each calendar year and sum annual inflows/outflows. At 2029 compute rent offset, required corpus, supported income, surplus/shortfall, earliest sustainable date, and whether every later enabled goal is funded.

- [ ] **Step 6: Run projection tests and verify GREEN**

Run the same projection pytest command. Expected: all tests PASS.

- [ ] **Step 7: Commit**

```powershell
git add backend/app/services/family_wealth_projection.py backend/tests/services/test_family_wealth_projection.py
git commit -m "feat: calculate family wealth runway"
```

## Task 4: Orchestrate persistence, portfolio values, and atomic updates

**Files:**
- Create: `backend/app/services/family_wealth_plan_service.py`
- Modify: `backend/tests/services/test_family_wealth_plan_service.py`

- [ ] **Step 1: Write failing service tests**

Create a latest snapshot containing INR financial assets, property, and land. Assert that the service passes financial assets separately from property, persists a complete update atomically, leaves settings unchanged on invalid input, and uses new starting values after a second workbook snapshot without altering plan assumptions.

```python
def test_new_snapshot_refreshes_starting_wealth_but_not_assumptions(session, seeded_plan):
    first = get_family_plan_response(session, today=date(2026, 7, 15))
    add_newer_snapshot(session, financial_value=500_000_000)
    second = get_family_plan_response(session, today=date(2026, 7, 15))
    assert second.assumptions == first.assumptions
    assert second.snapshot_id != first.snapshot_id
    assert second.scenario_projections[1].annual_points[0].financial_assets_inr > first.scenario_projections[1].annual_points[0].financial_assets_inr
```

- [ ] **Step 2: Run service tests and verify RED**

Run: `$env:PYTHONPATH='backend;.'; .\.venv\Scripts\python.exe -m pytest backend/tests/services/test_family_wealth_plan_service.py -q`

Expected: FAIL because the service is absent.

- [ ] **Step 3: Implement read orchestration**

Load the singleton plan and ordered goals, load the three existing primary-goal scenario rows, obtain the latest snapshot, classify `property` and `land` as real estate and all other supported assets as financial assets, convert supported foreign holdings through snapshot FX metadata, and call the pure projection engine once per scenario.

- [ ] **Step 4: Implement atomic update and restore defaults**

Use `with session.begin():` to update the plan, replace linked goals, and update scenario return values. Synchronize the existing primary goal's three `monthly_contribution_inr` fields to the plan-level base monthly contribution so the compatibility API and consolidated planner never disagree. Validate the complete response before leaving the transaction. Implement `restore_family_plan_defaults(session, today)` using the same canonical default factory used by migration tests.

- [ ] **Step 5: Run service tests and verify GREEN**

Run the same service pytest command. Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add backend/app/services/family_wealth_plan_service.py backend/tests/services/test_family_wealth_plan_service.py
git commit -m "feat: manage family wealth plan"
```

## Task 5: Expose family-plan APIs with stable validation errors

**Files:**
- Modify: `backend/app/api/v1/wealth_portfolio.py`
- Create: `backend/tests/api/test_family_wealth_plan_api.py`

- [ ] **Step 1: Write failing API tests**

Test:

```python
def test_get_family_plan(client):
    response = client.get("/api/v1/wealth-portfolio/goals/family-plan")
    assert response.status_code == 200
    assert response.json()["primary_goal"]["goal"]["target_amount_inr"] == 150_000_000

def test_invalid_family_plan_update_is_atomic(client, session, valid_payload):
    before = client.get("/api/v1/wealth-portfolio/goals/family-plan").json()
    valid_payload["assumptions"]["withdrawal_rate_pct"] = 0
    response = client.put("/api/v1/wealth-portfolio/goals/family-plan", json=valid_payload)
    assert response.status_code == 422
    assert client.get("/api/v1/wealth-portfolio/goals/family-plan").json() == before
```

Also test restore defaults and empty-snapshot `data_health="empty"`.

- [ ] **Step 2: Run API tests and verify RED**

Run: `$env:PYTHONPATH='backend;.'; .\.venv\Scripts\python.exe -m pytest backend/tests/api/test_family_wealth_plan_api.py -q`

Expected: FAIL with 404 routes.

- [ ] **Step 3: Add routes**

Add:

```python
@router.get("/goals/family-plan", response_model=FamilyPlanResponse)
def family_plan(session: Session = Depends(get_session)) -> FamilyPlanResponse:
    return get_family_plan_response(session)

@router.put("/goals/family-plan", response_model=FamilyPlanResponse)
def update_family_plan(payload: FamilyPlanUpdate, session: Session = Depends(get_session)) -> FamilyPlanResponse:
    return save_family_plan(session, payload)

@router.post("/goals/family-plan/restore-defaults", response_model=FamilyPlanResponse)
def restore_family_plan(session: Session = Depends(get_session)) -> FamilyPlanResponse:
    return restore_family_plan_defaults(session)
```

Map domain validation errors to the existing request-validation envelope with stable field locations.

- [ ] **Step 4: Run API tests and backend family suite**

Run:

```powershell
$env:PYTHONPATH='backend;.'
.\.venv\Scripts\python.exe -m pytest backend/tests/api/test_family_wealth_plan_api.py backend/tests/services/test_family_wealth_projection.py backend/tests/services/test_family_wealth_plan_service.py backend/tests/api/test_wealth_goal_api.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/api/v1/wealth_portfolio.py backend/tests/api/test_family_wealth_plan_api.py
git commit -m "feat: expose family wealth plan API"
```

## Task 6: Add frontend contracts, API calls, and pure chart helpers

**Files:**
- Modify: `frontend/src/features/portfolio/wealthTypes.ts`
- Modify: `frontend/src/features/portfolio/wealthApi.ts`
- Modify: `frontend/src/features/portfolio/wealthApi.test.ts`
- Create: `frontend/src/features/portfolio/familyWealthMath.ts`
- Create: `frontend/src/features/portfolio/familyWealthMath.test.ts`

- [ ] **Step 1: Write failing API and transformation tests**

```typescript
it('loads and saves the consolidated family plan', async () => {
  mockedAxios.get.mockResolvedValueOnce({ data: familyPlan });
  expect(await fetchFamilyPlan()).toBe(familyPlan);
  expect(mockedAxios.get).toHaveBeenCalledWith('/api/v1/wealth-portfolio/goals/family-plan');
});

it('maps annual points and goal events into chart rows', () => {
  const rows = familyRunwayRows(familyPlan.scenario_projections);
  expect(rows[0]).toMatchObject({ year: 2026, expectedTotal: 80000000 });
  expect(rows.find((row) => row.events.length)?.events[0].goalKey).toBe('passive_income');
});
```

- [ ] **Step 2: Run tests and verify RED**

Run: `npm test -- --run src/features/portfolio/wealthApi.test.ts src/features/portfolio/familyWealthMath.test.ts`

Expected: FAIL because functions and types do not exist.

- [ ] **Step 3: Add exact TypeScript contracts and API functions**

Mirror backend snake_case names in `FamilyPlanResponse`, `FamilyPlanUpdate`, `FamilyScenarioSettings`, `LinkedGoalSettings`, `AnnualRunwayPoint`, `GoalHealth`, and `PassiveIncomeAnalysis`. Add `fetchFamilyPlan`, `updateFamilyPlan`, and `restoreFamilyPlanDefaults`.

- [ ] **Step 4: Implement pure formatting and chart mapping**

Export `familyRunwayRows`, `goalStatusColor`, `formatCrore`, `formatMonthlyIncome`, and `familyPlanProblemField`. Keep React and Recharts imports out of this file.

- [ ] **Step 5: Run tests and verify GREEN**

Run the same Vitest command. Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add frontend/src/features/portfolio/wealthTypes.ts frontend/src/features/portfolio/wealthApi.ts frontend/src/features/portfolio/wealthApi.test.ts frontend/src/features/portfolio/familyWealthMath.ts frontend/src/features/portfolio/familyWealthMath.test.ts
git commit -m "feat: add family wealth frontend contracts"
```

## Task 7: Build the runway chart and analysis cards

**Files:**
- Create: `frontend/src/features/portfolio/FamilyWealthRunwayChart.tsx`
- Create: `frontend/src/features/portfolio/FamilyGoalCards.tsx`
- Create: `frontend/src/features/portfolio/PassiveIncomePanel.tsx`
- Modify: `frontend/src/features/portfolio/WealthGoalWorkspace.test.tsx`

- [ ] **Step 1: Write failing render tests**

Assert accessible text for the chart, all linked goals, status reasons, rental offset, required corpus, later-goal protection, and no colour-only status:

```typescript
it('renders goal reasons and passive income protection', () => {
  const html = renderToStaticMarkup(<FamilyGoalCards goals={familyPlan.goal_health} />);
  expect(html).toContain('Child 1 education');
  expect(html).toContain('Funded with 14% safety margin');
  const income = renderToStaticMarkup(<PassiveIncomePanel analysis={familyPlan.passive_income} />);
  expect(income).toContain('Rent counts toward the ₹2 lakh target');
  expect(income).toContain('Later family goals remain protected');
});
```

- [ ] **Step 2: Run render tests and verify RED**

Run: `npm test -- --run src/features/portfolio/WealthGoalWorkspace.test.tsx`

Expected: FAIL because components do not exist.

- [ ] **Step 3: Implement the chart**

Use a responsive Recharts `LineChart` with clean unfilled lines. Render expected financial assets, property, and total net worth by default; allow conservative and optimistic total-net-worth overlays. Render goal events with labelled `ReferenceLine` markers and a custom tooltip listing annual contributions, rent, growth, expenses, and closing balances.

- [ ] **Step 4: Implement goal and income cards**

Use semantic headings, status text, icons by goal type, and accessible reasons. Use Green/Amber/Red accents plus labels. Show required corpus, rental contribution, supported income, surplus/shortfall, earliest sustainable date, and later-goal protection in `PassiveIncomePanel`.

- [ ] **Step 5: Run render tests and verify GREEN**

Run the same Vitest command. Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add frontend/src/features/portfolio/FamilyWealthRunwayChart.tsx frontend/src/features/portfolio/FamilyGoalCards.tsx frontend/src/features/portfolio/PassiveIncomePanel.tsx frontend/src/features/portfolio/WealthGoalWorkspace.test.tsx
git commit -m "feat: visualize family wealth runway"
```

## Task 8: Add editable assumptions and integrate the runway-first workspace

**Files:**
- Create: `frontend/src/features/portfolio/FamilyPlanAssumptions.tsx`
- Modify: `frontend/src/features/portfolio/WealthGoalWorkspace.tsx`
- Modify: `frontend/src/features/portfolio/WealthGoalWorkspace.test.tsx`

- [ ] **Step 1: Write failing interaction tests**

Test the ₹6 lakh default, the annual step-up checkbox, disabled percentage field when unchecked, local draft preservation, atomic Save payload, restore confirmation, server field errors, retry, and data-import empty state.

```typescript
it('enables the 6 percent step-up only when selected', () => {
  const html = renderToStaticMarkup(<FamilyPlanAssumptions value={defaultPlan} onChange={vi.fn()} />);
  expect(html).toContain('value="600000"');
  expect(html).toContain('Annual contribution step-up');
  expect(html).toMatch(/value="6"[^>]*disabled/);
});
```

- [ ] **Step 2: Run workspace tests and verify RED**

Run: `npm test -- --run src/features/portfolio/WealthGoalWorkspace.test.tsx`

Expected: FAIL because the editor and family-plan composition are absent.

- [ ] **Step 3: Implement the assumptions editor**

Use a focused reducer with accepted and draft states. Group Contribution, Rent, Property, Income, Scenario, and Linked Goals in an MUI drawer. Make every default editable. Enabling the step-up checkbox enables the percentage field. Preview changes remain client-side until Save; server response becomes the new accepted state.

- [ ] **Step 4: Integrate runway-first page order**

Keep the existing pinned primary-goal header first, then render the runway chart, goal cards, passive-income panel, scenario comparison, and assumptions drawer trigger. Switch the workspace query to `fetchFamilyPlan`; retain the current loading, empty, warning, retry, unsaved, and save-success patterns.

- [ ] **Step 5: Run workspace tests and frontend suite**

Run:

```powershell
npm test -- --run src/features/portfolio/WealthGoalWorkspace.test.tsx src/features/portfolio/wealthApi.test.ts src/features/portfolio/familyWealthMath.test.ts src/features/portfolio/PortfolioHub.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add frontend/src/features/portfolio/FamilyPlanAssumptions.tsx frontend/src/features/portfolio/WealthGoalWorkspace.tsx frontend/src/features/portfolio/WealthGoalWorkspace.test.tsx
git commit -m "feat: integrate family wealth goal workspace"
```

## Task 9: Full verification and rendered acceptance

**Files:**
- Modify only if verification exposes a defect in files already listed above.

- [ ] **Step 1: Run focused backend tests**

```powershell
$env:PYTHONPATH='backend;.'
.\.venv\Scripts\python.exe -m pytest backend/tests/test_migrations.py backend/tests/services/test_family_wealth_projection.py backend/tests/services/test_family_wealth_plan_service.py backend/tests/api/test_family_wealth_plan_api.py backend/tests/api/test_wealth_goal_api.py -q
```

Expected: all tests PASS with zero failures.

- [ ] **Step 2: Run the full frontend test suite**

Run: `npm test -- --run`

Expected: all tests PASS with zero failures.

- [ ] **Step 3: Run production build**

Run: `npm run build`

Expected: Vite exits 0. A chunk-size warning is acceptable; TypeScript or build errors are not.

- [ ] **Step 4: Exercise live APIs with the real imported snapshot**

Verify `GET /api/v1/wealth-portfolio/goals/family-plan` returns HTTP 200, snapshot ID, six goals, three projections, annual points, and passive-income analysis. PUT a reversible copy of the current payload and confirm HTTP 200; do not alter unrelated portfolio data.

- [ ] **Step 5: Render desktop and tablet views**

Open the Portfolio → Goals workspace at approximately 1440×900 and 900×1200. Confirm:

- No horizontal overflow.
- ₹15 Cr remains pinned.
- Runway labels and markers do not clip.
- Goal cards wrap cleanly.
- Assumptions drawer is usable.
- Step-up checkbox immediately changes the preview after selection.
- Tooltips show crore-labelled values and annual cash flows.

Capture screenshots as verification evidence.

- [ ] **Step 6: Review diff and commit verification fixes**

Run: `git diff --check` and `git status --short`. Preserve all unrelated user changes. If verification required fixes, commit only the family-runway files:

```powershell
git add backend/alembic/versions/20260715_0009_family_wealth_plan.py backend/app/repos/models.py backend/app/schemas/wealth_portfolio.py backend/app/services/family_wealth_projection.py backend/app/services/family_wealth_plan_service.py backend/app/api/v1/wealth_portfolio.py backend/tests frontend/src/features/portfolio
git commit -m "fix: complete family wealth runway verification"
```
