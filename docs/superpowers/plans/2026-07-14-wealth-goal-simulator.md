# Wealth Goal Simulator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Activate the Portfolio Goals tab with a persisted ₹15 Cr primary goal, configurable three-scenario projections, required-contribution analysis, and a responsive decision dashboard.

**Architecture:** SQLite stores one primary goal and three complete scenario records. A backend calculation service combines those settings with the latest consolidated wealth summary and exposes a single GET/PUT API contract; React Query renders and updates that contract without duplicating financial formulas in the browser.

**Tech Stack:** Python 3.11, FastAPI, Pydantic, SQLAlchemy, Alembic, SQLite, pytest, React 18, TypeScript, Material UI 6, React Query 5, Recharts 3, Vitest.

---

## File map

- Create `backend/alembic/versions/20260714_0008_wealth_goals.py`: goal/scenario tables and deterministic seed data.
- Modify `backend/app/repos/models.py`: `WealthGoal` and `WealthGoalScenario` ORM models.
- Modify `backend/app/schemas/wealth_portfolio.py`: editable settings, projection, trajectory, and response schemas.
- Create `backend/app/services/wealth_goal_service.py`: validation-independent projection mathematics and persisted goal orchestration.
- Modify `backend/app/api/v1/wealth_portfolio.py`: primary-goal GET and PUT endpoints.
- Create `backend/tests/services/test_wealth_goal_service.py`: formula and persistence tests.
- Create `backend/tests/api/test_wealth_goal_api.py`: endpoint and atomic-update tests.
- Modify `backend/tests/test_migrations.py`: seeded schema assertions.
- Modify `frontend/src/features/portfolio/wealthTypes.ts`: goal API types.
- Modify `frontend/src/features/portfolio/wealthApi.ts`: goal fetch/update calls.
- Create `frontend/src/features/portfolio/wealthGoalMath.ts`: display-only helpers such as progress clamping and currency labels; no projection formulas.
- Create `frontend/src/features/portfolio/WealthGoalChart.tsx`: required and scenario trajectory chart.
- Create `frontend/src/features/portfolio/WealthGoalWorkspace.tsx`: goal query, finish-line panel, metrics, form, and scenario cards.
- Create `frontend/src/features/portfolio/WealthGoalWorkspace.test.tsx`: UI state and mutation tests.
- Modify `frontend/src/features/portfolio/PortfolioHub.tsx`: render the workspace at tab index 4.
- Modify `frontend/src/features/portfolio/PortfolioHub.test.tsx`: verify goal-tab wiring.

### Task 1: Persist goal settings and defaults

**Files:**
- Create: `backend/alembic/versions/20260714_0008_wealth_goals.py`
- Modify: `backend/app/repos/models.py`
- Modify: `backend/tests/test_migrations.py`

- [ ] **Step 1: Write the failing migration test**

Add assertions after upgrading to head:

```python
tables = set(inspect(connection).get_table_names())
assert {"wealth_goals", "wealth_goal_scenarios"} <= tables
goal = connection.execute(text("SELECT target_amount_inr, deadline, is_primary FROM wealth_goals")).one()
assert goal == (150000000.0, "2029-12-31", 1)
returns = connection.execute(
    text("SELECT scenario_key, annual_return_pct FROM wealth_goal_scenarios ORDER BY display_order")
).all()
assert returns == [("conservative", 7.0), ("expected", 10.0), ("optimistic", 13.0)]
```

- [ ] **Step 2: Run the migration test and confirm it fails**

Run:

```powershell
$env:PYTHONPATH='backend;.'; .\.venv\Scripts\python.exe -m pytest backend/tests/test_migrations.py -q
```

Expected: failure because `wealth_goals` does not exist.

- [ ] **Step 3: Add the migration and ORM models**

Create tables with a one-to-many foreign key and unique `(goal_id, scenario_key)` constraint. Seed stable UUIDs so migration tests are deterministic:

```python
GOAL_ID = "00000000-0000-0000-0000-000000000015"
SCENARIOS = (
    ("00000000-0000-0000-0000-000000000071", "conservative", 7.0, 0),
    ("00000000-0000-0000-0000-000000000100", "expected", 10.0, 1),
    ("00000000-0000-0000-0000-000000000130", "optimistic", 13.0, 2),
)
```

Model fields:

```python
class WealthGoal(Base):
    __tablename__ = "wealth_goals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    target_amount_inr: Mapped[float] = mapped_column(Float)
    deadline: Mapped[date] = mapped_column(Date)
    is_primary: Mapped[bool] = mapped_column(Boolean, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

class WealthGoalScenario(Base):
    __tablename__ = "wealth_goal_scenarios"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    goal_id: Mapped[str] = mapped_column(ForeignKey("wealth_goals.id"), index=True)
    scenario_key: Mapped[str] = mapped_column(String(16))
    annual_return_pct: Mapped[float] = mapped_column(Float)
    monthly_contribution_inr: Mapped[float] = mapped_column(Float, default=0)
    display_order: Mapped[int] = mapped_column(Integer)
    __table_args__ = (UniqueConstraint("goal_id", "scenario_key"),)
```

- [ ] **Step 4: Run the migration test**

Run the command from Step 2. Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/alembic/versions/20260714_0008_wealth_goals.py backend/app/repos/models.py backend/tests/test_migrations.py
git commit -m "feat: persist primary wealth goal settings"
```

### Task 2: Implement deterministic goal calculations

**Files:**
- Create: `backend/app/services/wealth_goal_service.py`
- Create: `backend/tests/services/test_wealth_goal_service.py`

- [ ] **Step 1: Write failing unit tests for the formulas**

Cover zero-return contributions, compound growth, required contribution, already-funded goals, and the 50-year horizon:

```python
def test_project_balance_adds_monthly_contributions_at_zero_return():
    assert project_balance(100_000, 0, 10_000, 12) == pytest.approx(220_000)

def test_required_monthly_contribution_is_zero_when_growth_reaches_target():
    assert required_monthly_contribution(1_000_000, 1_050_000, 12, 10) == 0

def test_required_monthly_contribution_reaches_target():
    contribution = required_monthly_contribution(1_000_000, 2_000_000, 24, 10)
    assert project_balance(1_000_000, 10, contribution, 24) == pytest.approx(2_000_000, rel=1e-6)

def test_completion_date_returns_none_beyond_fifty_years():
    assert projected_completion_date(date(2026, 7, 14), 1, 1_000_000_000, 0, 0) is None
```

- [ ] **Step 2: Run the service tests and confirm import failure**

```powershell
$env:PYTHONPATH='backend;.'; .\.venv\Scripts\python.exe -m pytest backend/tests/services/test_wealth_goal_service.py -q
```

Expected: collection failure because the service module is absent.

- [ ] **Step 3: Implement pure financial functions**

Use monthly end-of-period contributions and guard the zero-rate formula:

```python
def project_balance(start: float, annual_return_pct: float, monthly: float, months: int) -> float:
    rate = annual_return_pct / 1200
    if rate == 0:
        return start + monthly * months
    growth = (1 + rate) ** months
    return start * growth + monthly * ((growth - 1) / rate)

def required_monthly_contribution(start: float, target: float, months: int, annual_return_pct: float) -> float:
    future_without_contributions = project_balance(start, annual_return_pct, 0, months)
    if future_without_contributions >= target:
        return 0.0
    rate = annual_return_pct / 1200
    if rate == 0:
        return (target - start) / months
    factor = ((1 + rate) ** months - 1) / rate
    return max(0.0, (target - start * (1 + rate) ** months) / factor)
```

Add helpers for whole months, monthly trajectory points, and bounded completion-date search. Use `calendar.monthrange` rather than adding fixed day counts.

- [ ] **Step 4: Run service tests**

Run the command from Step 2. Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/services/wealth_goal_service.py backend/tests/services/test_wealth_goal_service.py
git commit -m "feat: calculate wealth goal projections"
```

### Task 3: Expose validated persisted goal APIs

**Files:**
- Modify: `backend/app/schemas/wealth_portfolio.py`
- Modify: `backend/app/services/wealth_goal_service.py`
- Modify: `backend/app/api/v1/wealth_portfolio.py`
- Create: `backend/tests/api/test_wealth_goal_api.py`

- [ ] **Step 1: Write failing GET and PUT API tests**

```python
def test_get_primary_goal_returns_defaults_and_empty_health(client):
    response = client.get("/api/v1/wealth-portfolio/goals/primary")
    assert response.status_code == 200
    body = response.json()
    assert body["goal"]["target_amount_inr"] == 150000000
    assert body["data_health"] == "empty"
    assert body["current_value_inr"] is None

def test_put_primary_goal_persists_complete_configuration(client):
    payload = primary_goal_payload(target=160000000, expected_return=11)
    response = client.put("/api/v1/wealth-portfolio/goals/primary", json=payload)
    assert response.status_code == 200
    reloaded = client.get("/api/v1/wealth-portfolio/goals/primary").json()
    assert reloaded["goal"]["target_amount_inr"] == 160000000
    assert reloaded["scenarios"][1]["annual_return_pct"] == 11

def test_put_rejects_invalid_scenario_order_without_partial_update(client):
    original = client.get("/api/v1/wealth-portfolio/goals/primary").json()
    payload = primary_goal_payload(conservative_return=15, expected_return=10)
    assert client.put("/api/v1/wealth-portfolio/goals/primary", json=payload).status_code == 422
    assert client.get("/api/v1/wealth-portfolio/goals/primary").json()["goal"] == original["goal"]
```

- [ ] **Step 2: Run API tests and confirm route failure**

```powershell
$env:PYTHONPATH='backend;.'; .\.venv\Scripts\python.exe -m pytest backend/tests/api/test_wealth_goal_api.py -q
```

Expected: 404 responses.

- [ ] **Step 3: Add Pydantic contracts and orchestration**

Define `GoalSettings`, `GoalScenarioSettings`, `GoalConfigurationUpdate`, `GoalTrajectoryPoint`, `GoalScenarioProjection`, and `PrimaryGoalResponse`. Validate exact scenario keys and ordering in a model validator:

```python
@model_validator(mode="after")
def validate_scenarios(self):
    keys = [item.scenario_key for item in self.scenarios]
    if keys != ["conservative", "expected", "optimistic"]:
        raise ValueError("Scenarios must be conservative, expected, and optimistic")
    rates = [item.annual_return_pct for item in self.scenarios]
    if rates != sorted(rates):
        raise ValueError("Scenario returns must increase from conservative to optimistic")
    return self
```

Implement `get_primary_goal_response(session, today=date.today())` by loading the seeded goal, calling `build_summary`, and producing nullable calculations for an empty snapshot. Implement `update_primary_goal` inside `with session.begin():`, updating all records before recalculation.

- [ ] **Step 4: Add GET and PUT routes**

```python
@router.get("/goals/primary", response_model=PrimaryGoalResponse)
def primary_goal(session: Session = Depends(get_session)) -> PrimaryGoalResponse:
    return get_primary_goal_response(session)

@router.put("/goals/primary", response_model=PrimaryGoalResponse)
def update_goal(payload: GoalConfigurationUpdate, session: Session = Depends(get_session)) -> PrimaryGoalResponse:
    return update_primary_goal(session, payload)
```

- [ ] **Step 5: Run backend goal tests**

```powershell
$env:PYTHONPATH='backend;.'; .\.venv\Scripts\python.exe -m pytest backend/tests/services/test_wealth_goal_service.py backend/tests/api/test_wealth_goal_api.py backend/tests/test_migrations.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```powershell
git add backend/app/schemas/wealth_portfolio.py backend/app/services/wealth_goal_service.py backend/app/api/v1/wealth_portfolio.py backend/tests/api/test_wealth_goal_api.py
git commit -m "feat: expose configurable wealth goal API"
```

### Task 4: Add the typed frontend goal client

**Files:**
- Modify: `frontend/src/features/portfolio/wealthTypes.ts`
- Modify: `frontend/src/features/portfolio/wealthApi.ts`
- Modify: `frontend/src/features/portfolio/wealthApi.test.ts`
- Create: `frontend/src/features/portfolio/wealthGoalMath.ts`
- Create: `frontend/src/features/portfolio/wealthGoalMath.test.ts`

- [ ] **Step 1: Write failing client/helper tests**

```typescript
it('loads and updates the primary goal', async () => {
  mockedAxios.get.mockResolvedValueOnce({ data: goalResponse });
  expect(await fetchPrimaryGoal()).toEqual(goalResponse);
  expect(mockedAxios.get).toHaveBeenCalledWith('/api/v1/wealth-portfolio/goals/primary');

  mockedAxios.put.mockResolvedValueOnce({ data: goalResponse });
  await updatePrimaryGoal(goalUpdate);
  expect(mockedAxios.put).toHaveBeenCalledWith('/api/v1/wealth-portfolio/goals/primary', goalUpdate);
});

it('clamps only visual progress', () => {
  expect(progressFill(123)).toBe(100);
  expect(progressFill(-4)).toBe(0);
});
```

- [ ] **Step 2: Run tests and confirm missing exports**

```powershell
node node_modules\vitest\vitest.mjs --run src/features/portfolio/wealthApi.test.ts src/features/portfolio/wealthGoalMath.test.ts
```

Expected: failures for missing goal functions/types.

- [ ] **Step 3: Implement exact API types and client functions**

Mirror backend field names. The core response shape is:

```typescript
export type PrimaryGoalResponse = {
  goal: GoalSettings;
  scenarios: GoalScenarioProjection[];
  calculated_on: string;
  snapshot_id: string | null;
  current_value_inr: number | null;
  achieved_pct: number | null;
  remaining_inr: number | null;
  required_monthly_contribution_inr: number | null;
  required_trajectory: GoalTrajectoryPoint[];
  data_health: 'empty' | 'fresh' | 'warning' | 'unavailable';
};
```

Client calls:

```typescript
export const fetchPrimaryGoal = async () =>
  (await axios.get<PrimaryGoalResponse>('/api/v1/wealth-portfolio/goals/primary')).data;

export const updatePrimaryGoal = async (payload: GoalConfigurationUpdate) =>
  (await axios.put<PrimaryGoalResponse>('/api/v1/wealth-portfolio/goals/primary', payload)).data;
```

Keep only formatting/progress helpers in `wealthGoalMath.ts`; do not duplicate compounding logic.

- [ ] **Step 4: Run client/helper tests**

Run the command from Step 2. Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/features/portfolio/wealthTypes.ts frontend/src/features/portfolio/wealthApi.ts frontend/src/features/portfolio/wealthApi.test.ts frontend/src/features/portfolio/wealthGoalMath.ts frontend/src/features/portfolio/wealthGoalMath.test.ts
git commit -m "feat: add typed wealth goal client"
```

### Task 5: Build the goal workspace and chart

**Files:**
- Create: `frontend/src/features/portfolio/WealthGoalChart.tsx`
- Create: `frontend/src/features/portfolio/WealthGoalWorkspace.tsx`
- Create: `frontend/src/features/portfolio/WealthGoalWorkspace.test.tsx`

- [ ] **Step 1: Write failing rendering and interaction tests**

Mock React Query data and assert real decision content:

```typescript
it('renders finish-line progress and scenario decisions', () => {
  const html = renderToString(<WealthGoalWorkspaceView data={goalResponse} />);
  expect(html).toContain('₹15 Cr by 2029');
  expect(html).toContain('Required monthly investment');
  expect(html).toContain('Conservative');
  expect(html).toContain('Expected');
  expect(html).toContain('Optimistic');
});

it('keeps settings editable when portfolio data is empty', () => {
  render(<WealthGoalWorkspaceView data={{ ...goalResponse, data_health: 'empty', current_value_inr: null }} />);
  expect(screen.getByLabelText('Target amount')).toBeEnabled();
  expect(screen.getByText(/Import investment.xlsx/)).toBeVisible();
});

it('saves all scenario settings as one configuration', async () => {
  render(<WealthGoalWorkspace />);
  await user.clear(screen.getByLabelText('Expected annual return'));
  await user.type(screen.getByLabelText('Expected annual return'), '11');
  await user.click(screen.getByRole('button', { name: 'Save changes' }));
  expect(updatePrimaryGoal).toHaveBeenCalledWith(expect.objectContaining({
    scenarios: expect.arrayContaining([expect.objectContaining({ scenario_key: 'expected', annual_return_pct: 11 })]),
  }));
});
```

- [ ] **Step 2: Run the workspace test and confirm missing component failure**

```powershell
node node_modules\vitest\vitest.mjs --run src/features/portfolio/WealthGoalWorkspace.test.tsx
```

Expected: module-not-found failure.

- [ ] **Step 3: Implement the chart**

Merge trajectory arrays by date, then render `ResponsiveContainer`, `LineChart`, four unfilled `Line` elements, direct endpoint labels, tooltip, axes, and grid. Use:

```typescript
const COLORS = {
  required: '#64748B',
  conservative: '#F59E0B',
  expected: '#2563EB',
  optimistic: '#059669',
};
```

Disable animation when `useMediaQuery('(prefers-reduced-motion: reduce)')` is true. Give the chart container a fixed responsive height and `minWidth: 0`.

- [ ] **Step 4: Implement the workspace**

Use a `Paper` finish-line panel, CSS-width progress fill, four metrics, two-column projection/configuration grid, and three scenario cards. Use controlled form state initialized from query data and a mutation that invalidates `['wealth-primary-goal']` after success.

The finish-line fill must use:

```tsx
<Box sx={{ width: `${progressFill(data.achieved_pct ?? 0)}%`, height: '100%', bgcolor: '#2563EB' }} />
```

Form buttons:

```tsx
<Button type="submit" variant="contained" disabled={!dirty || mutation.isPending}>Save changes</Button>
<Button type="button" variant="text" onClick={restoreDefaults}>Restore defaults</Button>
```

Use field labels exactly as tested and translate backend 422 details into inline messages without clearing form state.

- [ ] **Step 5: Run the workspace test**

Run the command from Step 2. Expected: pass.

- [ ] **Step 6: Commit**

```powershell
git add frontend/src/features/portfolio/WealthGoalChart.tsx frontend/src/features/portfolio/WealthGoalWorkspace.tsx frontend/src/features/portfolio/WealthGoalWorkspace.test.tsx
git commit -m "feat: build wealth goal decision workspace"
```

### Task 6: Activate the Goals tab

**Files:**
- Modify: `frontend/src/features/portfolio/PortfolioHub.tsx`
- Modify: `frontend/src/features/portfolio/PortfolioHub.test.tsx`

- [ ] **Step 1: Write the failing hub test**

Use an interactive render and select Goals:

```typescript
render(<PortfolioHub investments={<div>Investments content</div>} />);
await user.click(screen.getByRole('tab', { name: 'Goals' }));
expect(screen.getByTestId('wealth-goal-workspace')).toBeVisible();
expect(screen.queryByText(/Goals will be activated/)).not.toBeInTheDocument();
```

- [ ] **Step 2: Run the hub test and confirm it fails**

```powershell
node node_modules\vitest\vitest.mjs --run src/features/portfolio/PortfolioHub.test.tsx
```

Expected: the future-phase alert is still rendered.

- [ ] **Step 3: Wire the goal workspace**

Import `WealthGoalWorkspace`, render it for `tab === 4`, and update the future-phase condition:

```tsx
{tab === 4 ? <WealthGoalWorkspace /> : null}
{![2, 4, 5].includes(tab) ? <Alert severity="info">...</Alert> : null}
```

- [ ] **Step 4: Run portfolio frontend tests**

```powershell
node node_modules\vitest\vitest.mjs --run src/features/portfolio/PortfolioHub.test.tsx src/features/portfolio/WealthGoalWorkspace.test.tsx src/features/portfolio/wealthApi.test.ts src/features/portfolio/wealthGoalMath.test.ts
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/features/portfolio/PortfolioHub.tsx frontend/src/features/portfolio/PortfolioHub.test.tsx
git commit -m "feat: activate portfolio goals tab"
```

### Task 7: Verify API-to-UI behavior and rendered layout

**Files:**
- Create: `backend/tests/e2e/test_wealth_goal_flow.py`
- Modify: `docs/data-storage.md`

- [ ] **Step 1: Add the end-to-end API test**

Import a workbook fixture, load the goal, update expected assumptions, and verify recalculation survives reload:

```python
def test_imported_wealth_drives_persisted_goal_projection(client):
    preview = upload_real_layout_fixture(client)
    client.post(f"/api/v1/wealth-portfolio/imports/{preview['preview_token']}/commit")
    before = client.get("/api/v1/wealth-portfolio/goals/primary").json()
    assert before["current_value_inr"] == 493000
    payload = editable_payload(before, expected_return=11, expected_monthly=100000)
    saved = client.put("/api/v1/wealth-portfolio/goals/primary", json=payload).json()
    reloaded = client.get("/api/v1/wealth-portfolio/goals/primary").json()
    assert reloaded["scenarios"][1]["annual_return_pct"] == 11
    assert reloaded["scenarios"][1]["projected_deadline_value_inr"] == saved["scenarios"][1]["projected_deadline_value_inr"]
```

- [ ] **Step 2: Document goal storage**

Add to `docs/data-storage.md`: goal settings are user-authored persisted configuration, scenarios do not alter imported snapshots, PUT is atomic, and projection output is calculated rather than stored.

- [ ] **Step 3: Run the focused backend suite**

```powershell
$env:PYTHONPATH='backend;.'; .\.venv\Scripts\python.exe -m pytest backend/tests/test_migrations.py backend/tests/services/test_wealth_goal_service.py backend/tests/api/test_wealth_goal_api.py backend/tests/e2e/test_wealth_goal_flow.py -q
```

Expected: all tests pass.

- [ ] **Step 4: Run the focused frontend suite and production build**

```powershell
cd frontend
node node_modules\vitest\vitest.mjs --run src/features/portfolio/PortfolioHub.test.tsx src/features/portfolio/WealthGoalWorkspace.test.tsx src/features/portfolio/wealthApi.test.ts src/features/portfolio/wealthGoalMath.test.ts
node node_modules\vite\bin\vite.js build
```

Expected: all tests pass and Vite exits 0. A chunk-size warning is non-blocking.

- [ ] **Step 5: Render and inspect desktop and tablet layouts**

Run the backend and Vite frontend, open `/portfolio`, select **Goals**, and capture 1600×1000 and 900×900 screenshots. Verify:

- finish-line progress is visible and numerically labeled;
- chart lines and endpoint labels are legible;
- configuration is beside the chart on desktop and stacked at tablet width;
- no horizontal page overflow occurs;
- save and restore controls remain visible;
- existing Investments tab still renders its tables and charts.

- [ ] **Step 6: Commit verification and documentation**

```powershell
git add backend/tests/e2e/test_wealth_goal_flow.py docs/data-storage.md
git commit -m "test: verify wealth goal flow end to end"
```

## Completion criteria

- The Goals tab contains real persisted data and no future-phase message.
- ₹15 Cr and 31 December 2029 are seeded but editable.
- 7%, 10%, and 13% scenario returns are seeded but editable.
- Settings persist across API reloads.
- Projections use consolidated net-worth market value and never mutate snapshots.
- Required monthly contribution and projected completion dates handle documented edge cases.
- Empty/import-needed and API-error states contain no fabricated wealth figures.
- Backend tests, frontend tests, production build, and desktop/tablet browser inspection pass.

