# Momentum Market Index Charts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Sensex and S&P 500 history charts in a Markets section above the existing open-trades/Century Ply chart on the Momentum page.

**Architecture:** A focused backend service maps public market keys to fixed Yahoo symbols and returns normalized chart points for an allow-listed range. A reusable frontend card fetches one index independently, renders the existing clean blue-line visual language, and is composed twice in a responsive Markets section.

**Tech Stack:** FastAPI, Pydantic, pandas/yfinance-compatible market repository, React, TypeScript, TanStack Query, MUI, Recharts, Pytest, Vitest

---

### Task 1: Market index history API

**Files:**
- Create: `backend/app/services/market_index_service.py`
- Create: `backend/app/api/v1/market_indices.py`
- Modify: `backend/app/api/v1/__init__.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/services/test_market_index_service.py`
- Create: `backend/tests/api/test_market_indices_api.py`

- [ ] **Step 1: Write failing service tests**

Test an injected history loader so no network is needed:

```python
def test_build_history_maps_sensex_and_normalizes_points():
    service = MarketIndexService(loader=fake_loader)
    result = service.build_history("sensex", "1y")
    assert result.symbol == "^BSESN"
    assert result.points == [MarketIndexPoint(on=date(2026, 1, 2), close=79_223.11)]

def test_build_history_rejects_unknown_market_and_range():
    with pytest.raises(ValueError):
        service.build_history("dow", "1y")
    with pytest.raises(ValueError):
        service.build_history("sensex", "10y")
```

- [ ] **Step 2: Run the tests and confirm RED**

Run: `python -m pytest backend/tests/services/test_market_index_service.py -q`

Expected: import failure because `market_index_service` does not exist.

- [ ] **Step 3: Implement the service and response models**

Define fixed mappings and immutable models:

```python
INDEXES = {
    "sensex": ("Sensex", "^BSESN"),
    "sp500": ("S&P 500", "^GSPC"),
}
RANGES = {"1m": "1mo", "6m": "6mo", "1y": "1y", "5y": "5y"}

class MarketIndexPoint(BaseModel):
    on: date
    close: float

class MarketIndexHistory(BaseModel):
    key: str
    name: str
    symbol: str
    range: str
    latest_value: float
    change: float
    change_pct: float
    points: list[MarketIndexPoint]
```

`MarketIndexService.build_history()` must validate both allow lists, call the loader with the mapped Yahoo symbol/period, remove invalid closes, sort chronologically, and compute change from the first to last selected point. Empty data raises `MarketIndexUnavailable`.

- [ ] **Step 4: Add API tests and endpoint**

Test `GET /api/v1/market-indices/sensex/history?range=1y`, an invalid key (`404`), invalid range (`422`), and upstream-unavailable (`503`). Register the router in `app.api.v1` and `app.main` under the existing `/api/v1` prefix.

- [ ] **Step 5: Run focused backend tests**

Run: `python -m pytest backend/tests/services/test_market_index_service.py backend/tests/api/test_market_indices_api.py -q`

Expected: all tests pass.

- [ ] **Step 6: Commit**

```powershell
git add backend/app/services/market_index_service.py backend/app/api/v1/market_indices.py backend/app/api/v1/__init__.py backend/app/main.py backend/tests/services/test_market_index_service.py backend/tests/api/test_market_indices_api.py
git commit -m "feat: add market index history api"
```

### Task 2: Reusable market chart card

**Files:**
- Create: `frontend/src/components/MarketIndexChartCard.tsx`
- Create: `frontend/src/components/MarketIndexChartCard.test.tsx`

- [ ] **Step 1: Write the failing component tests**

Mock Axios for a Sensex response and assert the title, formatted latest value, positive/negative change treatment, range controls, and retry message. Assert clicking `6M` requests `range=6m`.

```tsx
render(<MarketIndexChartCard marketKey="sensex" />);
expect(await screen.findByText('Sensex')).toBeInTheDocument();
await user.click(screen.getByRole('button', { name: '6M' }));
expect(mockedAxios.get).toHaveBeenLastCalledWith(
  '/api/v1/market-indices/sensex/history',
  expect.objectContaining({ params: { range: '6m' } }),
);
```

- [ ] **Step 2: Run the test and confirm RED**

Run: `npx vitest --run src/components/MarketIndexChartCard.test.tsx --pool=threads --maxWorkers=1 --minWorkers=1`

Expected: import failure because the component does not exist.

- [ ] **Step 3: Implement the card**

Use `useQuery` with key `['market-index-history', marketKey, range]`, `staleTime: 15 * 60 * 1000`, and independent retry. Render a `LineChart` with:

```tsx
<Line type="linear" dataKey="close" stroke="#2E90FA" strokeWidth={2} dot={false} />
```

Use a restrained horizontal grid, domain-derived Y axis, formatted dates, no area/gradient fill, and four compact range buttons (`1M`, `6M`, `1Y`, `5Y`). Loading uses a skeleton; failure preserves the card height and exposes Retry.

- [ ] **Step 4: Run the component test**

Run: `npx vitest --run src/components/MarketIndexChartCard.test.tsx --pool=threads --maxWorkers=1 --minWorkers=1`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/components/MarketIndexChartCard.tsx frontend/src/components/MarketIndexChartCard.test.tsx
git commit -m "feat: add reusable market index chart card"
```

### Task 3: Place Markets above open trades

**Files:**
- Modify: `frontend/src/pages/DashboardPage.tsx`
- Create: `frontend/src/pages/DashboardPage.markets.test.tsx`

- [ ] **Step 1: Write a failing placement test**

Render the dashboard with existing network hooks mocked and assert DOM order:

```tsx
const markets = screen.getByText('Markets — India & US');
const investments = screen.getByText('My investments — open trades');
expect(markets.compareDocumentPosition(investments) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
expect(screen.getByText('Sensex')).toBeInTheDocument();
expect(screen.getByText('S&P 500')).toBeInTheDocument();
```

- [ ] **Step 2: Run the placement test and confirm RED**

Run: `npx vitest --run src/pages/DashboardPage.markets.test.tsx --pool=threads --maxWorkers=1 --minWorkers=1`

Expected: Markets heading is absent.

- [ ] **Step 3: Compose the section**

Import `MarketIndexChartCard`, then insert before the current green “My investments” band:

```tsx
<SectionBand color="#7C3AED" label="Markets — India & US" />
<Grid container spacing={2} sx={{ px: { xs: 1, md: 2 } }}>
  <Grid item xs={12} lg={6}><MarketIndexChartCard marketKey="sensex" /></Grid>
  <Grid item xs={12} lg={6}><MarketIndexChartCard marketKey="sp500" /></Grid>
</Grid>
```

- [ ] **Step 4: Verify frontend**

Run:

```powershell
npx vitest --run src/components/MarketIndexChartCard.test.tsx src/pages/DashboardPage.markets.test.tsx --pool=threads --maxWorkers=1 --minWorkers=1
npm run build
```

Expected: tests and Vite production build pass. A chunk-size warning is acceptable; compilation errors are not.

- [ ] **Step 5: Verify the rendered page**

Launch backend and frontend, open the Momentum page, and confirm both chart cards render above Century Ply/open trades at desktop width and stack at mobile width. Change the range on one card and confirm the other card is unchanged.

- [ ] **Step 6: Commit**

```powershell
git add frontend/src/pages/DashboardPage.tsx frontend/src/pages/DashboardPage.markets.test.tsx
git commit -m "feat: add markets section to momentum dashboard"
```

### Task 4: Final regression verification

**Files:** No production changes expected.

- [ ] Run focused backend market-index tests.
- [ ] Run focused frontend market chart and placement tests.
- [ ] Run `npm run build`.
- [ ] Run `git diff --check` and confirm the working tree contains only intentional changes.
