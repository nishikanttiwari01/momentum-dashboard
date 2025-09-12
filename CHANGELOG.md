# Momentum Dashboard — Changelog

All notable changes to this project will be documented here.  
We follow a **phase-based versioning** (v0.x.0) where each phase corresponds to a locked milestone.

---
## v0.7.0 — Phase 7: Screener Read Path (2025-09-12)
- Implemented real **GET /api/v1/screener** backed by Parquet “scores” snapshots.
- Added filtering DSL (server-side):
  - Supported ops: `.eq`, `.neq` (ignored if not used), `.gt`, `.gte`, `.lt`, `.lte`, `.in`, `.like` (prefix).
  - Examples: `sector.in=Energy,IT`, `score.gte=70`, `symbol.like=REL%`.
- Added multi-key **sorting** and **pagination**:
  - `sort=score.desc,last.desc`, `page`, `per_page` (default 100; max 500).
- Snapshot selection:
  - `run_id` (direct) or `as_of=YYYY-MM-DD` (resolves to latest on/before date; currently falls back to latest).
- Response schema aligned to momentum table:
  - Fields include: `symbol, name, sector, last, change_pct, score, strength, rsi, adx, ret_12_1m, ret_6m, ret_3m, ret_1m, ret_1w, pct_from_52w_high, atr_pct, liquidity, vol_spike, pct_today, buy, reason, source, stale, badges, run_id, as_of, last_index`.
  - `ret_1w` provided (defaults to `null` if not in snapshot).
  - `badges` synthesized from booleans (e.g., `breakout`, `near_uc`) when present, else `[]`.
- **Swagger** shows documented params again (`run_id`, `as_of`, `sort`, `page`, `per_page`); filter DSL is entered as extra query params.
- **Repo layer** (`ScoresRepo`):
  - Arrow-based filter + sort + page; robust to missing columns; stable defaults.
- **Tests** (added):
  - `tests/repos/test_scores_repo.py`: filtering, sort, pagination, empty snapshot, badge synthesis.
  - `tests/api/test_screener_api.py`: API happy path, filters, run_id, empty snapshot.
- Status: **All tests passing** (30/30).


## v0.6.0 — Phase 6: Parquet Helpers (2025-09-12)
- Added **Parquet helpers** (`app/repos/parquet/datasets.py`) for market/universe data:
  - Atomic writer with temp → commit → `_SUCCESS` marker.
  - Schema versioning stored in `meta/{table}_schema_version.json`.
  - Rowcount checks and file locks for single-writer safety.
- Added **CLI smoke tool** (`app/tools/parquet_smoke.py`) to manually write/read snapshots.
- Implemented **automated tests** (`tests/test_parquet_datasets.py`):
  - Commit/abort roundtrips.
  - Metadata checks (`run_id`, `schema_version`).
  - Snapshot discovery (`latest_snapshot`).
- Verified **Zstd compression**, dictionary encoding, and statistics enabled.
- All tests passing (26/26).

---

## v0.5.0 — Phase 5: Idempotency & Invariants (2025-09-10)
- Implemented **Idempotency-Key validation**:
  - Invalid keys return **422 Problem+JSON** with `code="IDEMPOTENCY_INVALID"`.
  - Header-only POSTs return **200 OK** instead of 201.
  - Full POST with JSON returns **201 Created**.
- Fixed **Positions repo invariants**:
  - Stop-loss values can only increase (“stop never decreases”).
  - Added `session.flush()` to make writes visible immediately in tests.
- Hardened **Alembic migrations** on Windows:
  - Disposed SQLite engine on shutdown.
  - Used `NullPool` to prevent file locks.
- Added **custom Problem+JSON handlers** for 422/HTTP errors (always include `code`).
- All tests passing (20/20).

---

## v0.4.0 — Phase 4: Alembic Migrations (2025-09-08)
- Added Alembic `env.py` with models metadata resolved from `app.repos.models`.
- Configured migrations to run against SQLite (`data/local.db`).
- Verified **clean upgrade head** with test harness.
- Established repeatable migration pattern for future schema changes.

---

## v0.3.0 — Phase 3: Repos & UoW (2025-09-07)
- Introduced **Repository layer** with interfaces and SQLAlchemy models.
- Implemented `SqliteUnitOfWork` for scoped transactions.
- Added **positions repository**:
  - Lock entry price.
  - Update stop-loss.
  - Close/delete positions.
- Early tests for CRUD operations and invariants.

---

## v0.2.0 — Phase 2: App Factory & Error Handling (2025-09-06)
- Created **FastAPI app factory** (`create_app`) with lifespan management.
- Added middlewares:
  - `RequestLogMiddleware`
  - `RequestIdMiddleware`
- Configured **CORS** support.
- Implemented **Problem+JSON error responses** for validation errors.
- Registered exception handlers:
  - Validation → 422
  - HTTP exceptions → Problem JSON
  - Unhandled exceptions → 500 Problem JSON.

---

## v0.1.0 — Phase 1: Contracts & Skeleton (2025-09-05)
- Authored initial **OpenAPI contracts** (`contracts/openapi.yaml`).
- Defined endpoint list and operationIds.
- Added shared components:
  - Problem schema (with `code` enum).
  - Pagination.
  - RunSummary/RunDetail skeletons.
- Established **baseline test harness** with pytest and SQLite init.
