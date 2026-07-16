# Source-Ledger Annual Review Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Normalize CURRENT ASSET and FIXED ASSET history into a source-ledger, preserve BALANCE SHEET formula lineage as reporting-period selections, and calculate FY-2024–FY-2026 Annual Review values from those underlying facts.

**Architecture:** Add stable ledger assets, dated observations, property-capital cash flows, and reporting-period source links alongside the legacy snapshot tables. Workbook import writes the ledger atomically and idempotently; Annual Review prefers ledger calculations and falls back to legacy snapshots only when ledger data is absent.

**Tech Stack:** Python, openpyxl, Pydantic, SQLAlchemy, Alembic, FastAPI, Pytest, SQLite

---

## Checkpoint A: Parse source facts

### Task 1: Extend the workbook fixture with real source layouts

**Files:**
- Modify: `backend/tests/fixtures/wealth_workbook_factory.py`
- Modify: `backend/tests/services/test_wealth_workbook.py`

- [ ] Add CURRENT ASSET rows for two owners, dated market-only columns, paired principal/market columns, subtotal rows, and source notes.
- [ ] Add FIXED ASSET dated property observations and Brigade payment rows.
- [ ] Add BALANCE SHEET formulas referencing the underlying CURRENT ASSET and FIXED ASSET cells for FY-2024, FY-2025, and FY-2026.
- [ ] Write failing assertions for stable source assets, dated observations, property-capital flows, reporting-period source references, and report reconciliation controls.
- [ ] Run `pytest tests/services/test_wealth_workbook.py -q` and confirm the new assertions fail because the parser exposes only latest aggregates.

### Task 2: Parse source assets and observations

**Files:**
- Modify: `backend/app/services/wealth_workbook.py`
- Test: `backend/tests/services/test_wealth_workbook.py`

- [ ] Add immutable parser types `ParsedLedgerAsset`, `ParsedAssetObservation`, `ParsedLedgerCashFlow`, `ParsedReportingPeriod`, and `ParsedReportingSource`.
- [ ] Parse CURRENT ASSET rows 3 through the row before owner subtotals using owner, description, and category as stable identity.
- [ ] Parse row-1 dates and row-2 column roles; emit market-only or paired principal/market observations with exact cell lineage.
- [ ] Parse each FIXED ASSET property and every dated principal/market pair.
- [ ] Parse Brigade dated payments as `property_capital` cash flows linked to Brigade land.
- [ ] Skip formulas/totals as facts and retain them only as controls.
- [ ] Run the focused parser tests.

### Task 3: Parse reporting-period lineage and controls

**Files:**
- Modify: `backend/app/services/wealth_workbook.py`
- Test: `backend/tests/services/test_wealth_workbook.py`

- [ ] Resolve BALANCE SHEET formula references for financial principal, financial market, property principal, and property market rows by FY column.
- [ ] Store the referenced source sheet/cell and reporting label without copying the calculated total as a ledger fact.
- [ ] Retain cached BALANCE SHEET totals and gains only as reconciliation controls.
- [ ] Emit warnings when a formula reference cannot be resolved or a cached report total differs from referenced-source sums by more than ₹1.
- [ ] Verify expected FY-2024–FY-2026 parser results.

## Checkpoint B: Persist the ledger idempotently

### Task 4: Add ledger schema and migration

**Files:**
- Modify: `backend/app/repos/models.py`
- Create: `backend/alembic/versions/20260716_0012_source_wealth_ledger.py`
- Create: `backend/tests/services/test_wealth_ledger_import.py`

- [ ] Write failing model tests for stable asset uniqueness, observation fingerprint uniqueness, cash-flow fingerprint uniqueness, and reporting-period source uniqueness.
- [ ] Add `WealthAsset`, `WealthAssetObservation`, `WealthCashFlow`, `WealthReportingPeriod`, and `WealthReportingPeriodSource` models.
- [ ] Add indexes for asset class, observed date, cash-flow date/type, and reporting year.
- [ ] Run the focused persistence tests and confirm migration startup creates every ledger table.

### Task 5: Commit ledger facts atomically

**Files:**
- Modify: `backend/app/services/wealth_import_service.py`
- Modify: `backend/tests/services/test_wealth_import_service.py`

- [ ] Write failing tests proving ledger facts are inserted with import/cell lineage and legacy snapshot import remains intact.
- [ ] Upsert stable assets and insert idempotent observations, cash flows, periods, and source links inside the existing import transaction.
- [ ] When the workbook hash already exists but its ledger facts are absent, populate the ledger against the existing import instead of returning immediately.
- [ ] When ledger facts already exist for the same import/fingerprints, return without duplicates.
- [ ] Keep a failed ledger import atomic so existing source and override data remains unchanged.
- [ ] Run parser/import/ledger tests.

## Checkpoint C: Calculate Annual Review from source facts

### Task 6: Add a shared ledger query service

**Files:**
- Create: `backend/app/services/wealth_ledger_service.py`
- Create: `backend/tests/services/test_wealth_ledger_service.py`

- [ ] Write failing tests for source-observation resolution, reporting-period selection, actual observation dates, asset-class totals, and property-capital flows.
- [ ] Resolve each reporting-period source link to its underlying observations and aggregate without reading BALANCE SHEET totals.
- [ ] Return financial/property principal and market totals plus source dates and lineage.
- [ ] Add true 31 December point-in-time fallback only when no reporting selection exists.
- [ ] Run the focused ledger service tests.

### Task 7: Switch Annual Review to the ledger

**Files:**
- Modify: `backend/app/services/annual_review_service.py`
- Modify: `backend/app/schemas/wealth_portfolio.py`
- Modify: `backend/tests/services/test_annual_review_service.py`
- Modify: `backend/tests/api/test_annual_review_api.py`

- [ ] Write failing tests for FY-2024, FY-2025, and FY-2026 using ledger observations and reporting links.
- [ ] Calculate opening/closing wealth, additions, financial gain, and property gain from selected source facts.
- [ ] Preserve rent/XIRR as missing when source facts are insufficient and retain manual-override precedence.
- [ ] Add reporting label, selection method, and actual source dates to the API response.
- [ ] Keep legacy snapshot fallback for an installation without ledger rows.
- [ ] Verify ₹58,254,009.25, ₹82,510,481.25, ₹2,963,721, ₹83,058,852.25, and -₹513,229 checkpoints.

## Checkpoint D: Live workbook validation

### Task 8: Re-import and render the real data

**Files:**
- Modify only if validation exposes a covered parser defect.

- [ ] Run the focused parser, import, ledger, Annual Review, and API tests.
- [ ] Apply migration `20260716_0012` to `backend/data/local.db`.
- [ ] Re-import `D:\WORK\NEW_STOCK_DASHBOARD\investment.xlsx`; the existing-hash path must backfill ledger facts without duplicating the legacy snapshot.
- [ ] Query the live Annual Review API and compare FY-2024–FY-2026 against the workbook checkpoints.
- [ ] Render the Annual Review tab and verify reporting labels plus actual selected observation dates.
- [ ] Stop for user review before switching Overview, Properties, Goals, or other consumers to the ledger.
