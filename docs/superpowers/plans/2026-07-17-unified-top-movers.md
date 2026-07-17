# Unified Top Movers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the duplicate Top Performers card with one Top Movers experience supporting 1D through 5Y and validated custom date ranges.

**Architecture:** Extend the contract-first Top Movers API and move return-window resolution and batch adjusted-close ranking into a focused service. DashboardPage owns the period/custom controls and continues rendering the existing gainers and losers tables; the standalone performers component and endpoint are removed after migration.

**Tech Stack:** FastAPI, Pydantic, PyArrow/Parquet, pytest, React 18, TypeScript, Material UI, TanStack Query, Vitest, Testing Library, OpenAPI, Orval.

---

## File structure

- Create `backend/app/services/top_movers_service.py`: date-window resolution, one batch Parquet scan, adjusted-close boundary selection, and deterministic ranking.
- Create `backend/tests/services/test_top_movers_service.py`: focused calculation and missing-data tests.
- Modify `backend/app/api/v1/screener.py`: validate request parameters, obtain the current universe, call the service, and delete the performers route.
- Modify `backend/tests/api/test_screener_api.py`: endpoint presets, custom validation, response metadata, and retired-route coverage.
- Modify `contracts/openapi.yaml`: expanded period enum, custom query dates, and resolved-date response fields.
- Regenerate `backend/app/schemas/generated/models.py`, `frontend/src/lib/api/client.ts`, and relevant files under `frontend/src/lib/api/types/` from the contract.
- Modify `frontend/src/pages/DashboardPage.tsx`: unified controls and layout; remove TopPerformersCard usage.
- Create `frontend/src/pages/DashboardPage.top-movers.test.tsx`: interaction and request tests.
- Modify `frontend/src/pages/DashboardPage.markets.test.tsx`: remove the obsolete component mock.
- Delete `frontend/src/components/TopPerformersCard.tsx`: duplicated UI and direct Axios client.

### Task 1: Add the historical-return ranking service

**Files:**
- Create: `backend/tests/services/test_top_movers_service.py`
- Create: `backend/app/services/top_movers_service.py`

- [ ] **Step 1: Write failing window and ranking tests**

Create a test table with `symbol`, `dt`, `close`, and `adj_close`. Cover a weekend boundary, split-adjusted prices, missing history, and stable tie ordering:

```python
from datetime import date
import pyarrow as pa

from app.services.top_movers_service import rank_returns, resolve_window


def test_resolve_window_uses_true_trailing_year():
    assert resolve_window("1y", date(2026, 7, 17), None, None) == (
        date(2025, 7, 17), date(2026, 7, 17)
    )


def test_rank_returns_uses_nearest_in_range_adjusted_closes():
    table = pa.table({
        "symbol": ["AAA", "AAA", "BBB", "BBB", "MISS"],
        "dt": ["2026-01-05", "2026-01-09", "2026-01-05", "2026-01-09", "2026-01-09"],
        "close": [100.0, 120.0, 50.0, 45.0, 10.0],
        "adj_close": [50.0, 60.0, 50.0, 45.0, 10.0],
    })
    result = rank_returns(table, {"AAA", "BBB", "MISS"}, date(2026, 1, 3), date(2026, 1, 10))
    assert [(row.symbol, row.return_pct) for row in result] == [("AAA", 20.0), ("BBB", -10.0)]
    assert result[0].start_date.isoformat() == "2026-01-05"
    assert result[0].end_date.isoformat() == "2026-01-09"
```

- [ ] **Step 2: Run tests and verify the missing module failure**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/services/test_top_movers_service.py -q`

Expected: FAIL during collection because `app.services.top_movers_service` does not exist.

- [ ] **Step 3: Implement date resolution and pure ranking**

Define immutable `ReturnRow` records; use `relativedelta` for calendar months/years, select the earliest valid adjusted close on or after the requested start and latest on or before the requested end, omit symbols without two nonzero endpoints, and sort by `(-return_pct, symbol)`:

```python
@dataclass(frozen=True)
class ReturnRow:
    symbol: str
    return_pct: float
    start_date: date
    end_date: date


PERIOD_DELTAS = {
    "1d": relativedelta(days=1), "1w": relativedelta(weeks=1),
    "1m": relativedelta(months=1), "3m": relativedelta(months=3),
    "6m": relativedelta(months=6), "1y": relativedelta(years=1),
    "5y": relativedelta(years=5),
}


def resolve_window(period: str, end: date, start_date: date | None, end_date: date | None) -> tuple[date, date]:
    if period == "custom":
        assert start_date is not None and end_date is not None
        return start_date, end_date
    return end - PERIOD_DELTAS[period], end
```

Implement `load_and_rank_returns(symbols, start, end)` with exactly one `datasets.scan("prices", run_id=None, dt_range=..., columns=["symbol", "dt", "close", "adj_close"])` call, falling back from null `adj_close` to `close` row-by-row.

- [ ] **Step 4: Run the focused service tests**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/services/test_top_movers_service.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the service**

```powershell
git add backend/app/services/top_movers_service.py backend/tests/services/test_top_movers_service.py
git commit -m "feat: rank movers from historical adjusted prices"
```

### Task 2: Extend and validate the Top Movers API

**Files:**
- Modify: `backend/tests/api/test_screener_api.py`
- Modify: `backend/app/api/v1/screener.py`

- [ ] **Step 1: Add failing endpoint tests**

Parameterize `1d`, `1w`, `1m`, `3m`, `6m`, `1y`, and `5y`; mock the service and assert it receives the resolved boundaries. Add this validation matrix:

```python
@pytest.mark.parametrize("query", [
    "period=custom",
    "period=custom&start_date=2026-01-01",
    "period=custom&end_date=2026-01-31",
    "period=custom&start_date=2026-02-01&end_date=2026-01-01",
    "period=1m&start_date=2026-01-01&end_date=2026-01-31",
])
def test_top_movers_rejects_invalid_date_parameters(client, query):
    response = client.get(f"/api/v1/screener/top-movers?{query}")
    assert response.status_code == 400
```

Assert a successful custom response includes `requested_start_date`, `requested_end_date`, `resolved_start_date`, and `resolved_end_date`. Assert `GET /api/v1/screener/top-performers` returns 404.

- [ ] **Step 2: Run endpoint tests and observe failures**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/api/test_screener_api.py -k "top_movers or top_performers" -q`

Expected: FAIL because long/custom periods and metadata are unsupported and the old route still exists.

- [ ] **Step 3: Replace field-based endpoint ranking with the service**

Change the signature to typed dates and enforce one parameter mode:

```python
def get_top_movers(
    period: str = Query("1d", pattern="^(1d|1w|1m|3m|6m|1y|5y|custom)$"),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
) -> TopMovers:
```

For `custom`, require both dates and `start_date <= end_date`; for presets, reject either date. Read the current screened rows once to retain names, sectors, prices, scores, eligibility, and drawer actions. Pass their symbols to `load_and_rank_returns`, create the first five gainers and first five losers, and report the common actual boundary dates. Raise `HTTPException(400, detail={"code": "no_trading_data", ...})` when no stock has a valid pair. Delete `PERFORMER_PERIOD_FIELD`, `PERFORMER_COLUMNS`, and `get_top_performers`.

- [ ] **Step 4: Run endpoint and service tests**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/api/test_screener_api.py backend/tests/services/test_top_movers_service.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the API migration**

```powershell
git add backend/app/api/v1/screener.py backend/tests/api/test_screener_api.py
git commit -m "feat: unify mover periods and custom ranges"
```

### Task 3: Update the OpenAPI contract and generated clients

**Files:**
- Modify: `contracts/openapi.yaml`
- Regenerate: `backend/app/schemas/generated/models.py`
- Regenerate: `frontend/src/lib/api/client.ts`
- Regenerate: `frontend/src/lib/api/types/getTopMoversParams.ts`
- Regenerate: `frontend/src/lib/api/types/getTopMoversPeriod.ts`
- Regenerate: `frontend/src/lib/api/types/topMovers.ts`
- Regenerate: `frontend/src/lib/api/types/topMoversPeriod.ts`

- [ ] **Step 1: Expand the contract**

Set the period enum to `["1d", "1w", "1m", "3m", "6m", "1y", "5y", "custom"]`. Add nullable `start_date` and `end_date` query parameters with `format: date`. Add nullable date properties `requested_start_date`, `requested_end_date`, `resolved_start_date`, and `resolved_end_date` to `TopMovers`. Remove the undocumented performers operation if present.

- [ ] **Step 2: Regenerate backend models**

Run from `backend`:

`..\.venv\Scripts\datamodel-codegen.exe --input ..\contracts\openapi.yaml --input-file-type openapi --output app\schemas\generated\models.py --output-model-type pydantic_v2.BaseModel --target-python-version 3.11 --use-double-quotes --use-standard-collections --enum-field-as-literal all --collapse-root-models --encoding utf-8`

Expected: exit 0 and `TopMovers.period` accepts all eight values.

- [ ] **Step 3: Regenerate the frontend client**

Run from `frontend`: `npm run codegen`

Expected: exit 0 and `GetTopMoversParams` contains `period`, `start_date`, and `end_date`.

- [ ] **Step 4: Verify generated artifacts**

Run: `rg -n "custom|resolved_start_date|start_date" contracts/openapi.yaml backend/app/schemas/generated/models.py frontend/src/lib/api/types frontend/src/lib/api/client.ts`

Expected: matches in the contract and both generated clients; no manual edits in generated files.

- [ ] **Step 5: Commit contract artifacts**

```powershell
git add contracts/openapi.yaml backend/app/schemas/generated/models.py frontend/src/lib/api
git commit -m "feat: expand top movers contract"
```

### Task 4: Consolidate the Momentum page UI

**Files:**
- Create: `frontend/src/pages/DashboardPage.top-movers.test.tsx`
- Modify: `frontend/src/pages/DashboardPage.tsx`
- Modify: `frontend/src/pages/DashboardPage.markets.test.tsx`
- Delete: `frontend/src/components/TopPerformersCard.tsx`

- [ ] **Step 1: Write failing UI tests**

Mock `useGetTopMovers`, capture its params, render DashboardPage with the existing surrounding components mocked, and assert all controls exist and no Top Performers heading exists:

```tsx
expect(screen.getByRole('button', { name: '6 Months' })).toBeTruthy();
expect(screen.getByRole('button', { name: '1 Year' })).toBeTruthy();
expect(screen.getByRole('button', { name: '5 Years' })).toBeTruthy();
expect(screen.getByRole('button', { name: 'Custom' })).toBeTruthy();
expect(screen.queryByText('Top Performers')).toBeNull();
```

Click Custom, assert start/end fields appear, verify Apply stays disabled until both valid dates exist, verify reversed dates show `Start date must be on or before end date`, then enter `2026-01-03` and `2026-01-10`, click Apply, and expect captured params to equal `{ period: 'custom', start_date: '2026-01-03', end_date: '2026-01-10' }`. Assert ETF Watch's grid item has `lg=12` through a test id on its wrapper.

- [ ] **Step 2: Run the UI test and verify failures**

Run from `frontend`: `npm test -- --run src/pages/DashboardPage.top-movers.test.tsx`

Expected: FAIL because long/custom controls do not exist and Top Performers still renders.

- [ ] **Step 3: Implement unified controls and layout**

Expand `PERIOD_OPTIONS`, using generated enum values. Keep draft custom dates separate from applied query state so typing does not issue requests. On preset selection, clear the applied dates. On valid Apply, set `{ period: 'custom', start_date, end_date }`. Render two `TextField type="date"` controls and an Apply button only for Custom. Display the API's resolved range next to the snapshot timestamp when present.

Remove the `TopPerformersCard` import and grid item. Change ETF Watch to a full-width grid item and add `data-testid="etf-watch-grid"`. Delete `TopPerformersCard.tsx`; remove its mock from the markets composition test.

- [ ] **Step 4: Run focused frontend tests**

Run from `frontend`: `npm test -- --run src/pages/DashboardPage.top-movers.test.tsx src/pages/DashboardPage.markets.test.tsx`

Expected: PASS.

- [ ] **Step 5: Commit UI consolidation**

```powershell
git add frontend/src/pages/DashboardPage.tsx frontend/src/pages/DashboardPage.top-movers.test.tsx frontend/src/pages/DashboardPage.markets.test.tsx
git add -u frontend/src/components/TopPerformersCard.tsx
git commit -m "feat: consolidate top movers dashboard UI"
```

### Task 5: Full verification and documentation consistency

**Files:**
- Modify only if a verification failure exposes a defect in a file already listed above.

- [ ] **Step 1: Run the full backend suite**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests -q`

Expected: PASS with no Top Performers route expectations remaining.

- [ ] **Step 2: Run frontend tests, type build, and lint**

Run from `frontend`:

```powershell
npm test -- --run
npm run build
npm run lint
```

Expected: all tests pass, TypeScript build exits 0, and lint exits 0.

- [ ] **Step 3: Check obsolete references and diffs**

Run:

```powershell
rg -n "TopPerformersCard|Top Performers|top-performers" backend frontend contracts
git diff --check
git status --short
```

Expected: no obsolete runtime/test/contract references, no whitespace errors, and only intentional changes are present.

- [ ] **Step 4: Commit any verification fixes**

If verification required edits, stage only those named files and commit:

```powershell
git add backend/app/services/top_movers_service.py backend/app/api/v1/screener.py backend/tests frontend/src/pages contracts/openapi.yaml backend/app/schemas/generated/models.py frontend/src/lib/api
git commit -m "fix: complete unified top movers verification"
```

- [ ] **Step 5: Record final evidence**

Run: `git status --short; git log -5 --oneline`

Expected: clean working tree and commits for service, API, contract, UI, plus any verification fix.
