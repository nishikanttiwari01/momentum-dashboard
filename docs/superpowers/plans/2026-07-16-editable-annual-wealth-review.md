# Editable Annual Wealth Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a persistent Annual Review that derives existing portfolio values and stores only manual overrides for incomplete or corrected fields.

**Architecture:** A nullable per-year override table sits above existing portfolio snapshots, assets, transactions, valuations, and family-plan data. A service assembles effective annual values with field-level provenance and reconciliation; the React tab edits overrides through four focused endpoints.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Pydantic, SQLite/PostgreSQL-compatible SQL, React, TypeScript, TanStack Query, Material UI, Recharts, Pytest, Vitest

---

## Checkpoint 1: Backend annual-review foundation

### Task 1: Add override persistence

**Files:**
- Modify: `backend/app/repos/models.py`
- Create: `backend/alembic/versions/20260716_0011_annual_review_overrides.py`
- Test: `backend/tests/services/test_annual_review_service.py`

- [ ] Write a failing persistence test creating two overrides for the same year and expecting the unique constraint to reject duplication.
- [ ] Add `PortfolioAnnualReviewOverride` with unique integer `year`, nullable numeric override columns, nullable notes, and timestamps.
- [ ] Add migration `20260716_0011` after `20260716_0010` creating and dropping `portfolio_annual_review_overrides`.
- [ ] Run `pytest tests/services/test_annual_review_service.py -q` and confirm the persistence test passes.

### Task 2: Define the annual-review contract

**Files:**
- Modify: `backend/app/schemas/wealth_portfolio.py`
- Test: `backend/tests/services/test_wealth_schemas.py`

- [ ] Write failing schema tests for valid nullable overrides and rejection of negative opening, closing, contribution, rent, or withdrawal values.
- [ ] Add `AnnualReviewOverrideUpdate`, `AnnualReviewField`, `AnnualReviewReconciliation`, and `AnnualReviewResponse` schemas.
- [ ] Constrain year to 2000 through the runtime current year and XIRR to -100 through 1,000.
- [ ] Run the focused schema tests.

### Task 3: Assemble derived values without duplication

**Files:**
- Create: `backend/app/services/annual_review_service.py`
- Test: `backend/tests/services/test_annual_review_service.py`

- [ ] Write failing tests for snapshot boundary selection, INR asset totals, financial/property separation, transaction aggregation, missing data remaining null, and manual override precedence.
- [ ] Implement `list_annual_reviews`, `get_annual_review`, `save_annual_review_overrides`, and `delete_annual_review_overrides`.
- [ ] Convert USD assets and transactions using persisted effective FX rates when available; return missing source status when conversion is unavailable.
- [ ] Calculate reconciliation only when every required effective value is present.
- [ ] Keep actual rent and historical goal outflows missing unless persisted actual records exist; never use future projections as actuals.
- [ ] Run `pytest tests/services/test_annual_review_service.py -q`.

### Task 4: Expose annual-review endpoints

**Files:**
- Modify: `backend/app/api/v1/wealth_portfolio.py`
- Create: `backend/tests/api/test_annual_review_api.py`

- [ ] Write failing API tests for list, get, upsert, delete, missing year, and validation errors.
- [ ] Add GET collection, GET year, PUT year, and DELETE year routes under `/annual-reviews`.
- [ ] Ensure PUT and DELETE commit only override rows and return the freshly assembled review.
- [ ] Run `pytest tests/api/test_annual_review_api.py tests/services/test_annual_review_service.py -q`.

### Task 5: Backend checkpoint verification

**Files:**
- No production changes.

- [ ] Run the focused annual-review API/service/schema tests.
- [ ] Run Alembic upgrade against the configured local database and verify the new table exists.
- [ ] Commit only backend annual-review files and report the API checkpoint before UI work.

## Checkpoint 2: Editable Annual Review UI

### Task 6: Add frontend transport and types

**Files:**
- Modify: `frontend/src/features/portfolio/wealthTypes.ts`
- Modify: `frontend/src/features/portfolio/wealthApi.ts`
- Modify: `frontend/src/features/portfolio/wealthApi.test.ts`

- [ ] Write failing tests for list/get/put/delete URL and payload behaviour.
- [ ] Add field-source, reconciliation, annual-review response, and override update types matching Pydantic field names.
- [ ] Add `fetchAnnualReviews`, `fetchAnnualReview`, `saveAnnualReviewOverrides`, and `deleteAnnualReviewOverrides`.
- [ ] Run `npm test -- --run src/features/portfolio/wealthApi.test.ts`.

### Task 7: Build the editor drawer

**Files:**
- Create: `frontend/src/features/portfolio/AnnualReviewEditor.tsx`
- Create: `frontend/src/features/portfolio/AnnualReviewEditor.test.tsx`

- [ ] Write failing tests for prefilled effective values, source badges, changed-field payloads, restore calculated value, validation, and delete confirmation.
- [ ] Build compact rupee inputs for opening, contributions, investment gain/loss, property gain/loss, rent, withdrawals, closing, XIRR, and notes.
- [ ] Track dirty override fields separately so unchanged calculated values are never copied into override storage.
- [ ] Add Save changes, Restore calculated values, and Delete overrides actions.
- [ ] Run the focused editor tests.

### Task 8: Replace mock Annual Review data

**Files:**
- Modify: `frontend/src/features/portfolio/PortfolioAnnualReview.tsx`
- Create: `frontend/src/features/portfolio/PortfolioAnnualReview.test.tsx`

- [ ] Write failing view tests for loading, empty, incomplete, reconciled, needs-review, edit, save failure, and year switching.
- [ ] Replace hardcoded reviews with TanStack Query data from `fetchAnnualReviews`.
- [ ] Render source badges on summary values and use effective values for the bridge and scorecard.
- [ ] Add `Add year` and `Edit year` actions opening `AnnualReviewEditor`.
- [ ] Invalidate the annual-review query after save or delete.
- [ ] Use correct UTF-8 rupee, minus, and separator characters throughout the rewritten component.
- [ ] Run the focused Annual Review and PortfolioHub tests.

### Task 9: Final verification

**Files:**
- No production changes.

- [ ] Run focused backend annual-review tests.
- [ ] Run focused frontend Annual Review, API, and PortfolioHub tests.
- [ ] Run `npm run build`.
- [ ] Review the diff to confirm existing portfolio source tables and unrelated dirty files were not modified.
- [ ] Commit only Annual Review implementation files and report the UI for manual review before any additional portfolio section is changed.
