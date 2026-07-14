# US QQQ Portfolio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add BUY-only QQQ transaction entry, USD holding metrics, and a ranged price chart with purchase markers and average cost to the Portfolio page.

**Architecture:** A new backend US-portfolio service owns validated CSV persistence, QQQ price retrieval/cache, and derived holding/history responses. A dedicated FastAPI router exposes this service. Focused React components consume those endpoints and are mounted below the existing mutual-fund content, keeping INR and USD state independent.

**Tech Stack:** Python 3, FastAPI, Pydantic v2, CSV, yfinance, pytest; React 18, TypeScript, Material UI, TanStack Query, Recharts, Vitest, Testing Library.

---

## File Structure

- Create `configs/us_portfolio.yaml`: configurable QQQ instrument metadata and cache policy.
- Create `data/us_portfolio_transactions.csv`: header-only source of truth for US BUY transactions.
- Create `backend/app/services/us_portfolio_service.py`: validation-independent domain calculations, atomic CSV repository, yfinance adapter/cache, overview/history builders.
- Create `backend/app/api/v1/us_portfolio.py`: request model and three HTTP endpoints.
- Modify `backend/app/api/v1/__init__.py` and `backend/app/main.py`: register the router.
- Create `backend/tests/services/test_us_portfolio_service.py`: calculation, persistence, history, and failure tests.
- Create `backend/tests/api/test_us_portfolio_api.py`: route and validation tests.
- Create `frontend/src/features/portfolio/usPortfolioTypes.ts`: stable client-side contract types and USD formatting.
- Create `frontend/src/features/portfolio/AddUsTransactionDialog.tsx`: controlled BUY form.
- Create `frontend/src/features/portfolio/UsInvestmentChart.tsx`: ranged price chart, buy markers, average line, and transaction table.
- Create `frontend/src/features/portfolio/UsInvestmentsSection.tsx`: independent queries, summary table, expansion, and dialog orchestration.
- Modify `frontend/src/pages/Portfolio.tsx`: mount the new section without coupling its loading/error state to Indian funds.
- Create `frontend/src/features/portfolio/UsInvestmentsSection.test.tsx` and `frontend/src/test/setup.ts`: focused UI coverage.
- Modify `frontend/vite.config.ts`: activate jsdom and the shared test setup.

### Task 1: Transaction Domain and Atomic CSV Persistence

**Files:**
- Create: `backend/app/services/us_portfolio_service.py`
- Create: `backend/tests/services/test_us_portfolio_service.py`
- Create: `configs/us_portfolio.yaml`
- Create: `data/us_portfolio_transactions.csv`

- [ ] **Step 1: Write failing calculation and persistence tests**

```python
from datetime import datetime, timezone
from pathlib import Path
import pytest
from app.services import us_portfolio_service as service


def buy(txn_id: str, quantity: float, price: float, fees: float = 0.0):
    return service.BuyTransaction(
        id=txn_id, instrument_id="qqq", purchased_at=datetime(2026, 7, 1, 14, 30, tzinfo=timezone.utc),
        quantity=quantity, price_usd=price, fees_usd=fees,
    )


def test_summary_includes_fees_in_weighted_average():
    result = service.calculate_holding([buy("a", 1, 400, 2), buy("b", 2, 430, 3)], latest_price=450)
    assert result["total_units"] == 3
    assert result["total_invested_usd"] == 1265
    assert result["average_buy_price_usd"] == pytest.approx(421.6667, abs=0.0001)
    assert result["current_value_usd"] == 1350
    assert result["unrealized_gain_usd"] == 85


def test_repository_round_trip_and_rejected_write_is_unchanged(tmp_path: Path):
    path = tmp_path / "transactions.csv"
    repo = service.TransactionRepository(path)
    saved = repo.add(buy("a", 0.5, 500))
    assert repo.list_for("qqq") == [saved]
    before = path.read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        repo.add(buy("b", 0, 500))
    assert path.read_text(encoding="utf-8") == before
```

- [ ] **Step 2: Run tests and confirm the missing module failure**

Run: `python -m pytest backend/tests/services/test_us_portfolio_service.py -v`
Expected: FAIL because `us_portfolio_service` does not exist.

- [ ] **Step 3: Implement the transaction model, calculations, and repository**

Implement `BuyTransaction`, `calculate_holding`, and `TransactionRepository`. Use columns `id,instrument_id,purchased_at,quantity,price_usd,fees_usd`; validate finite positive quantity/price, non-negative fees, timezone-aware timestamps, and supported instrument IDs. Write to a sibling temporary file with `newline=""`, flush and `os.fsync`, then call `os.replace(temp_path, self.path)`.

```python
@dataclass(frozen=True)
class BuyTransaction:
    id: str
    instrument_id: str
    purchased_at: datetime
    quantity: float
    price_usd: float
    fees_usd: float = 0.0


def calculate_holding(rows: list[BuyTransaction], latest_price: float | None) -> dict[str, float | None]:
    units = sum(row.quantity for row in rows)
    invested = sum(row.quantity * row.price_usd + row.fees_usd for row in rows)
    average = invested / units if units else None
    value = units * latest_price if latest_price is not None else None
    gain = value - invested if value is not None else None
    return {
        "total_units": round(units, 6), "total_invested_usd": round(invested, 2),
        "average_buy_price_usd": round(average, 4) if average is not None else None,
        "current_value_usd": round(value, 2) if value is not None else None,
        "unrealized_gain_usd": round(gain, 2) if gain is not None else None,
        "unrealized_gain_pct": round(gain * 100 / invested, 2) if gain is not None and invested else None,
    }
```

Add QQQ configuration with `id: qqq`, `ticker: QQQ`, `currency: USD`, and a 12-hour cache TTL. Add only the CSV header to the data file.

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest backend/tests/services/test_us_portfolio_service.py -v`
Expected: PASS for calculations, fractional quantities, empty holdings, validation, and CSV preservation.

- [ ] **Step 5: Commit the domain slice**

```bash
git add configs/us_portfolio.yaml data/us_portfolio_transactions.csv backend/app/services/us_portfolio_service.py backend/tests/services/test_us_portfolio_service.py
git commit -m "feat: add US portfolio transaction domain"
```

### Task 2: QQQ Price Adapter, Cache, Overview, and Chart Payload

**Files:**
- Modify: `backend/app/services/us_portfolio_service.py`
- Modify: `backend/tests/services/test_us_portfolio_service.py`

- [ ] **Step 1: Write failing deterministic history tests**

```python
def test_build_history_returns_buys_and_average(monkeypatch, tmp_path):
    repo = service.TransactionRepository(tmp_path / "transactions.csv")
    repo.add(buy("a", 1, 400, 2))
    monkeypatch.setattr(service, "fetch_price_history", lambda *args, **kwargs: [
        (date(2026, 7, 1), 405.0), (date(2026, 7, 2), 410.0)
    ])
    result = service.build_history("qqq", "1m", repo=repo)
    assert result["points"][-1] == {"date": "2026-07-02", "price": 410.0}
    assert result["purchases"][0]["price_usd"] == 400
    assert result["average_buy_price_usd"] == 402


def test_overview_keeps_costs_when_prices_fail(monkeypatch, tmp_path):
    repo = service.TransactionRepository(tmp_path / "transactions.csv")
    repo.add(buy("a", 1, 400))
    monkeypatch.setattr(service, "fetch_price_history", lambda *args, **kwargs: [])
    row = service.build_overview(repo=repo)["instruments"][0]
    assert row["holding"]["total_invested_usd"] == 400
    assert row["holding"]["current_value_usd"] is None
    assert row["market_data_error"] == "No QQQ market-price data available"
```

- [ ] **Step 2: Run tests and verify missing builder failures**

Run: `python -m pytest backend/tests/services/test_us_portfolio_service.py -v`
Expected: FAIL because `fetch_price_history`, `build_overview`, and `build_history` are missing.

- [ ] **Step 3: Implement yfinance retrieval and stale cache fallback**

Fetch adjusted daily closes with `yf.Ticker("QQQ").history(period="max", interval="1d", auto_adjust=True, actions=False)`. Normalize dates to ISO calendar dates and finite prices. Cache `{fetched_at, points}` under `data/us_portfolio_cache/QQQ.json`; return valid stale cache when a refresh fails, and expose `stale` plus `latest_price_date` in service responses.

- [ ] **Step 4: Implement overview and ranged history builders**

Use the same day windows as the mutual-fund chart (`31`, `183`, `366`, `1830`, and unlimited). Return daily `{date, price}` points, visible BUY events with exact timestamp/quantity/price/fees/invested amount, fee-inclusive average cost, and `latest_vs_average_pct`. Keep all transactions in the overview newest-first. Accept injected `repo` and fetch function boundaries for deterministic tests.

- [ ] **Step 5: Run focused tests and commit**

Run: `python -m pytest backend/tests/services/test_us_portfolio_service.py -v`
Expected: PASS, including stale/no-price behavior.

```bash
git add backend/app/services/us_portfolio_service.py backend/tests/services/test_us_portfolio_service.py
git commit -m "feat: calculate QQQ portfolio market metrics"
```

### Task 3: FastAPI Contracts and Routes

**Files:**
- Create: `backend/app/api/v1/us_portfolio.py`
- Create: `backend/tests/api/test_us_portfolio_api.py`
- Modify: `backend/app/api/v1/__init__.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write failing endpoint tests**

```python
from fastapi.testclient import TestClient
from app.main import app
from app.api.v1 import us_portfolio


def test_create_buy_returns_201_and_refreshes_overview(monkeypatch):
    captured = {}
    monkeypatch.setattr(us_portfolio.service, "add_buy", lambda payload: captured.update(payload) or {"id": "txn-1", **payload})
    response = TestClient(app).post("/api/v1/portfolio/us/transactions", json={
        "instrument_id": "qqq", "purchased_at": "2026-07-01T14:30:00Z",
        "quantity": 1.5, "price_usd": 500, "fees_usd": 1,
    })
    assert response.status_code == 201
    assert captured["quantity"] == 1.5


def test_create_buy_rejects_zero_quantity():
    response = TestClient(app).post("/api/v1/portfolio/us/transactions", json={
        "instrument_id": "qqq", "purchased_at": "2026-07-01T14:30:00Z",
        "quantity": 0, "price_usd": 500, "fees_usd": 0,
    })
    assert response.status_code == 422
```

- [ ] **Step 2: Run route tests and confirm 404/import failure**

Run: `python -m pytest backend/tests/api/test_us_portfolio_api.py -v`
Expected: FAIL because the router is not registered.

- [ ] **Step 3: Add request validation and endpoints**

Define a `BuyTransactionCreate(BaseModel)` with `instrument_id: Literal["qqq"]`, timezone-aware `purchased_at`, `quantity: PositiveFloat`, `price_usd: PositiveFloat`, and `fees_usd: Annotated[float, Field(ge=0)] = 0`. Add:

```python
@router.get("/overview")
def overview(refresh: bool = False): ...

@router.get("/{instrument_id}/history")
def history(instrument_id: Literal["qqq"], range: Literal["1m", "6m", "1y", "5y", "max"] = "1y"): ...

@router.post("/transactions", status_code=201)
def create_transaction(payload: BuyTransactionCreate): ...
```

Register the router with prefix `/portfolio/us` under the existing `/api/v1` prefix.

- [ ] **Step 4: Run API and route regression tests**

Run: `python -m pytest backend/tests/api/test_us_portfolio_api.py backend/tests/test_routes_json.py -v`
Expected: PASS with all three new routes present.

- [ ] **Step 5: Commit the API slice**

```bash
git add backend/app/api/v1/us_portfolio.py backend/app/api/v1/__init__.py backend/app/main.py backend/tests/api/test_us_portfolio_api.py
git commit -m "feat: expose QQQ portfolio APIs"
```

### Task 4: US Investment Summary and BUY Dialog

**Files:**
- Create: `frontend/src/features/portfolio/usPortfolioTypes.ts`
- Create: `frontend/src/features/portfolio/AddUsTransactionDialog.tsx`
- Create: `frontend/src/features/portfolio/UsInvestmentsSection.tsx`
- Create: `frontend/src/features/portfolio/UsInvestmentsSection.test.tsx`
- Create: `frontend/src/test/setup.ts`
- Modify: `frontend/vite.config.ts`

- [ ] **Step 1: Configure jsdom and write a failing form-flow test**

Set `test.environment` to `jsdom`, load `src/test/setup.ts`, and import `@testing-library/jest-dom/vitest` there. Mock Axios and render with a fresh `QueryClientProvider`.

```tsx
it('adds a BUY and refreshes the US overview', async () => {
  mockedAxios.get.mockResolvedValue({ data: overviewFixture });
  mockedAxios.post.mockResolvedValue({ data: { id: 'txn-1' } });
  renderSection();
  await user.click(await screen.findByRole('button', { name: /add transaction/i }));
  await user.type(screen.getByLabelText(/quantity/i), '1.5');
  await user.type(screen.getByLabelText(/price per unit/i), '500');
  await user.click(screen.getByRole('button', { name: /^save purchase$/i }));
  await waitFor(() => expect(mockedAxios.post).toHaveBeenCalledWith(
    '/api/v1/portfolio/us/transactions', expect.objectContaining({ quantity: 1.5, price_usd: 500 })
  ));
});
```

- [ ] **Step 2: Run the test and confirm missing component failure**

Run: `npm test -- --run src/features/portfolio/UsInvestmentsSection.test.tsx`
Expected: FAIL because `UsInvestmentsSection` does not exist.

- [ ] **Step 3: Implement types, USD formatting, summary table, and dialog**

Define exact response types matching Task 3. Use `Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })`. Query `/api/v1/portfolio/us/overview` independently. Render latest price, units, invested, average price, current value, and gain/loss. The dialog owns string inputs, converts them only on submit, validates finite positive quantity/price and non-negative fees, posts the ISO timestamp, leaves the dialog open on errors, and invalidates `['us-portfolio-overview']` plus `['us-portfolio-history', 'qqq']` after success.

- [ ] **Step 4: Add empty, validation, USD, and provider-error assertions**

Verify zero holdings show an Add first purchase prompt; invalid values do not call POST; `$1,265.00` and `$421.67` render for the fixture; and `market_data_error` leaves stored transaction/cost content visible.

- [ ] **Step 5: Run and commit the summary/form slice**

Run: `npm test -- --run src/features/portfolio/UsInvestmentsSection.test.tsx`
Expected: PASS.

```bash
git add frontend/vite.config.ts frontend/src/test/setup.ts frontend/src/features/portfolio
git commit -m "feat: add QQQ transaction form and summary"
```

### Task 5: Ranged Chart, Purchase Markers, and Transaction Table

**Files:**
- Create: `frontend/src/features/portfolio/UsInvestmentChart.tsx`
- Modify: `frontend/src/features/portfolio/UsInvestmentsSection.tsx`
- Modify: `frontend/src/features/portfolio/UsInvestmentsSection.test.tsx`

- [ ] **Step 1: Write failing chart payload and interaction tests**

Expand QQQ, assert the history request uses `range: '1y'`, click 6M and assert `range: '6m'`. With a fixture containing two purchases, assert both accessible purchase descriptions, `Average cost $421.67`, `Latest price is 6.72% above average cost`, and newest-first transaction dates.

- [ ] **Step 2: Run the focused test and verify chart assertions fail**

Run: `npm test -- --run src/features/portfolio/UsInvestmentsSection.test.tsx`
Expected: FAIL because no chart/history query exists.

- [ ] **Step 3: Implement the chart**

Use a Recharts `ComposedChart`: `Line` for daily `price`, `Scatter` for purchases mapped to `{dateLabel, fullDate, purchasePrice, transaction}`, and `ReferenceLine y={average_buy_price_usd}` with a dashed stroke. Preserve the actual purchase price rather than snapping its Y value to the day's close. Include range toggles, loading/empty/error states, the above/below-average label, tooltip details, and a newest-first Material UI transaction table.

- [ ] **Step 4: Run frontend tests and production build**

Run: `npm test -- --run src/features/portfolio/UsInvestmentsSection.test.tsx`
Expected: PASS.

Run: `npm run build`
Expected: TypeScript and Vite build complete successfully.

- [ ] **Step 5: Commit the visualization slice**

```bash
git add frontend/src/features/portfolio/UsInvestmentChart.tsx frontend/src/features/portfolio/UsInvestmentsSection.tsx frontend/src/features/portfolio/UsInvestmentsSection.test.tsx
git commit -m "feat: chart QQQ purchases and average cost"
```

### Task 6: Portfolio Integration and Full Verification

**Files:**
- Modify: `frontend/src/pages/Portfolio.tsx`
- Modify: `.gitignore` only if runtime cache/temp patterns are not already ignored.

- [ ] **Step 1: Add an integration assertion for independent rendering**

Mock the Indian overview as configured and the US overview as successful, then verify both `Mutual Fund Portfolio` and `US Investments` render. In a second case reject only the US request and verify the Indian funds table remains visible alongside a US-specific error alert.

- [ ] **Step 2: Run the test and verify the section is not mounted**

Run: `npm test -- --run src/features/portfolio/UsInvestmentsSection.test.tsx`
Expected: FAIL because `Portfolio.tsx` does not yet render the section.

- [ ] **Step 3: Mount the section below Indian fund content**

Import and render `<UsInvestmentsSection />` after the mutual-fund table and before Other instruments. Do not include its loading state in the existing Portfolio early return. Stop row-click propagation on Add transaction and form controls.

- [ ] **Step 4: Run all targeted verification**

Run: `python -m pytest backend/tests/services/test_us_portfolio_service.py backend/tests/api/test_us_portfolio_api.py backend/tests/test_routes_json.py -v`
Expected: PASS.

Run: `npm test -- --run src/features/portfolio/UsInvestmentsSection.test.tsx`
Expected: PASS.

Run: `npm run build`
Expected: PASS with no TypeScript errors.

Run: `git diff --check`
Expected: no whitespace errors.

- [ ] **Step 5: Commit the integrated feature**

```bash
git add frontend/src/pages/Portfolio.tsx .gitignore
git commit -m "feat: integrate US investments into portfolio"
```

- [ ] **Step 6: Perform a final scope audit**

Confirm QQQ is USD-only, BUY-only, does not alter INR totals, persists through the API, renders exact purchase dots and a fee-inclusive current average line, survives missing market prices, and leaves Indian mutual-fund transaction entry for a later release.
