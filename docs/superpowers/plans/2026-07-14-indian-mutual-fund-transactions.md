# Indian Mutual-Fund Transactions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add QQQ-style BUY entry, combined average NAV, purchase markers, and transaction tables to every configured Indian mutual fund.

**Architecture:** Extend the existing portfolio service and CSV ledger rather than creating a second Indian data path. Add validated atomic writes and enrich the existing overview/history responses, then extract focused React form/chart pieces while preserving the current Portfolio table and INR calculations.

**Tech Stack:** Python, FastAPI, Pydantic, CSV, pytest; React, TypeScript, Material UI, TanStack Query, Recharts, Vite.

---

## File Map

- Modify `backend/app/services/portfolio_service.py`: normalized BUY creation, atomic persistence, combined cost basis, transaction payloads, and chart events.
- Modify `backend/app/api/v1/portfolio.py`: validated Indian BUY endpoint and instrument-aware history request.
- Create `backend/tests/services/test_portfolio_transactions.py`: derivation, validation, accounts, persistence, aggregation, and chart tests.
- Create `backend/tests/api/test_portfolio_transactions_api.py`: request validation and route behavior.
- Create `frontend/src/features/portfolio/AddFundTransactionDialog.tsx`: INR mutual-fund BUY form.
- Create `frontend/src/features/portfolio/FundNavChart.tsx`: existing NAV graph plus purchase scatter, average line, comparison label, and ledger table.
- Modify `frontend/src/pages/Portfolio.tsx`: use focused components and add summary/action columns.

### Task 1: Normalize and Persist Indian BUY Transactions

**Files:**
- Test: `backend/tests/services/test_portfolio_transactions.py`
- Modify: `backend/app/services/portfolio_service.py`

- [ ] **Step 1: Write failing transaction-normalization tests**

```python
def test_amount_and_nav_derive_units():
    row = service.normalize_buy({"instrument_id": "axis_midcap", "date": "2026-07-14", "amount": 10000, "nav": 250, "fees": 10})
    assert row.units == 40
    assert row.amount == 10000


def test_units_and_nav_derive_amount():
    row = service.normalize_buy({"instrument_id": "axis_midcap", "date": "2026-07-14", "units": 40, "nav": 250, "fees": 0})
    assert row.amount == 10000


def test_inconsistent_amount_and_units_are_rejected():
    with pytest.raises(ValueError, match="do not match"):
        service.normalize_buy({"instrument_id": "axis_midcap", "date": "2026-07-14", "amount": 9000, "units": 40, "nav": 250})
```

- [ ] **Step 2: Run tests to prove RED**

Run: `.\.venv\Scripts\python.exe -m pytest backend/tests/services/test_portfolio_transactions.py -q -p no:cacheprovider`
Expected: FAIL because `normalize_buy` does not exist.

- [ ] **Step 3: Implement normalization and hidden account assignment**

Add `normalize_buy(payload, config=None) -> Txn`. Parse the ISO date; require a configured mutual-fund ID and its first `holdings_config` row; require positive finite NAV and either amount or units; derive the missing value; accept both only when `abs(amount - units * nav) <= max(0.01, amount * 0.0001)`; require non-negative finite fees; return a BUY `Txn` using the first configured account.

- [ ] **Step 4: Add failing atomic-write test**

```python
def test_append_transaction_preserves_existing_rows(tmp_path, monkeypatch):
    path = tmp_path / "portfolio_transactions.csv"
    path.write_text("date,instrument_id,account_id,type,amount,units,nav,fees\n2026-01-01,axis_midcap,nre_primary,BUY,1000,4,250,0\n", encoding="utf-8")
    monkeypatch.setattr(service, "TRANSACTIONS_PATH", path)
    service.append_buy({"instrument_id": "axis_midcap", "date": "2026-07-14", "amount": 10000, "nav": 250})
    rows = service.load_transactions()
    assert len(rows) == 2
    assert rows[-1].account_id == "nre_primary"
```

- [ ] **Step 5: Implement atomic persistence and run tests**

Write the current valid ledger plus the normalized row through a sibling temporary file, flush and `os.fsync`, then `os.replace`. Preserve the standard header and all parsed valid rows. Run the focused test command; expected PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/portfolio_service.py backend/tests/services/test_portfolio_transactions.py
git commit -m "feat: persist Indian fund purchases"
```

### Task 2: Combined Cost Basis and Purchase-Aware NAV History

**Files:**
- Modify: `backend/app/services/portfolio_service.py`
- Modify: `backend/tests/services/test_portfolio_transactions.py`

- [ ] **Step 1: Write failing combined-account tests**

```python
def test_combined_summary_includes_fees_across_accounts():
    rows = [txn("nre", 10, 100, 5), txn("nro", 5, 120, 0)]
    result = service.calculate_fund_holding(rows, latest_nav=130)
    assert result["total_units"] == 15
    assert result["total_invested"] == 1605
    assert result["average_nav"] == 107
    assert result["gain"] == 345
```

- [ ] **Step 2: Run and confirm RED**

Expected: FAIL because `calculate_fund_holding` and purchase-enriched history are absent.

- [ ] **Step 3: Implement one combined holding calculation**

Aggregate BUY and SIP rows for the instrument regardless of account. Use amount plus fees for invested cost, total units for average NAV, and latest NAV for value/gain. Add `average_nav`, `gain`, and `gain_pct` to each mutual fund's overview totals and expose newest-first transaction payloads on the instrument.

- [ ] **Step 4: Write and pass ranged marker tests**

Call `build_nav_history(scheme_code, "1y", instrument_id="axis_midcap")` with injected transactions and NAV history. Assert purchase events use their transaction NAV, older events are excluded from a limited range, average NAV uses all current purchases, and `latest_vs_average_pct` is correct. Implement optional `instrument_id`, `purchases`, `average_nav`, and comparison fields without changing existing callers.

- [ ] **Step 5: Run service tests and commit**

Run both portfolio transaction and existing US portfolio service tests; expected PASS.

```bash
git add backend/app/services/portfolio_service.py backend/tests/services/test_portfolio_transactions.py
git commit -m "feat: calculate mutual fund average NAV"
```

### Task 3: Indian BUY API Contract

**Files:**
- Modify: `backend/app/api/v1/portfolio.py`
- Create: `backend/tests/api/test_portfolio_transactions_api.py`

- [ ] **Step 1: Write failing API tests**

```python
def test_create_fund_buy_returns_201(monkeypatch):
    monkeypatch.setattr(portfolio.portfolio_service, "append_buy", lambda payload: {"instrument_id": payload["instrument_id"]})
    response = TestClient(app).post("/api/v1/portfolio/transactions", json={
        "instrument_id": "axis_midcap", "date": "2026-07-14", "amount": 10000, "nav": 250, "fees": 10
    })
    assert response.status_code == 201


def test_create_fund_buy_rejects_missing_amount_and_units():
    response = TestClient(app).post("/api/v1/portfolio/transactions", json={
        "instrument_id": "axis_midcap", "date": "2026-07-14", "nav": 250
    })
    assert response.status_code == 422
```

- [ ] **Step 2: Run and confirm route failure**

Expected: FAIL with 404.

- [ ] **Step 3: Implement request model and endpoints**

Define `FundBuyCreate` with instrument ID, date, positive optional amount/units, positive NAV, and non-negative fees. A model validator requires amount or units. POST `/transactions` delegates deeper consistency/account validation to `append_buy` and maps `ValueError` to HTTP 422. Add `instrument_id` to `/nav_history` and pass it to the service.

- [ ] **Step 4: Run API regression tests and commit**

Run new API tests plus `test_routes_json.py`; expected PASS.

```bash
git add backend/app/api/v1/portfolio.py backend/tests/api/test_portfolio_transactions_api.py
git commit -m "feat: expose Indian fund purchase API"
```

### Task 4: BUY Dialog and Fund Summary Integration

**Files:**
- Create: `frontend/src/features/portfolio/AddFundTransactionDialog.tsx`
- Modify: `frontend/src/pages/Portfolio.tsx`

- [ ] **Step 1: Add a failing UI test or pure form-validation test**

Verify NAV plus amount derives a valid request, NAV plus units derives a valid request, neither amount nor units blocks submission, and clicking Add transaction does not expand/collapse the row.

- [ ] **Step 2: Run test to prove RED**

Run the focused Vitest command; expected failure because the dialog does not exist. If the repository's frontend test environment cannot run, retain the test and use the TypeScript production build as the executable integration gate.

- [ ] **Step 3: Implement the dialog**

Mirror the QQQ dialog styling. Submit `{instrument_id,date,amount?,units?,nav,fees}` to `/api/v1/portfolio/transactions`; show backend validation errors; close only after save; invalidate `portfolio-overview` and the active fund's `nav-history` queries.

- [ ] **Step 4: Add summary fields and action**

Extend the instrument type with transaction payloads and new totals. Add Units, Average NAV, and Gain/loss columns plus Add transaction. Use INR formatting and stop propagation on the action.

- [ ] **Step 5: Run frontend test/build and commit**

Run focused tests when available and `npm run build`; expected successful compilation.

```bash
git add frontend/src/features/portfolio/AddFundTransactionDialog.tsx frontend/src/pages/Portfolio.tsx
git commit -m "feat: add mutual fund purchase form"
```

### Task 5: Purchase Markers, Average Line, and Ledger Table

**Files:**
- Create: `frontend/src/features/portfolio/FundNavChart.tsx`
- Modify: `frontend/src/pages/Portfolio.tsx`

- [ ] **Step 1: Add failing chart behavior assertions**

With two transaction fixtures, assert two purchase descriptions, the fee-inclusive average NAV label, latest-above/below text, and newest-first ledger rows. Assert changing 1Y to 6M sends the selected range and instrument ID.

- [ ] **Step 2: Run to prove RED**

Expected: FAIL because the existing inline chart has no purchase series.

- [ ] **Step 3: Extract and enhance `FundNavChart`**

Move the existing chart into the focused file. Use `ComposedChart`, the existing NAV `Line`, a purchase `Scatter` keyed to actual transaction NAV/date, and a dashed `ReferenceLine` at average NAV. Render tooltips, comparison text, offline warning, empty-purchase guidance, and a newest-first transaction table below the chart.

- [ ] **Step 4: Run frontend verification and commit**

Run focused tests and `npm run build`; expected PASS.

```bash
git add frontend/src/features/portfolio/FundNavChart.tsx frontend/src/pages/Portfolio.tsx
git commit -m "feat: plot mutual fund purchases on NAV charts"
```

### Task 6: Full Verification and Main Push

- [ ] **Step 1: Run backend verification**

Run: `.\.venv\Scripts\python.exe -m pytest backend/tests/services/test_portfolio_transactions.py backend/tests/api/test_portfolio_transactions_api.py backend/tests/services/test_us_portfolio_service.py backend/tests/api/test_us_portfolio_api.py backend/tests/test_routes_json.py -q -p no:cacheprovider`
Expected: all tests pass.

- [ ] **Step 2: Run frontend production build**

Run: `npm run build` from `frontend`.
Expected: Vite build succeeds without TypeScript errors.

- [ ] **Step 3: Audit and push**

Run `git diff --check`, confirm only intended files are staged, commit any final integration adjustments, then `git push origin main`. Preserve all unrelated unstaged files.
