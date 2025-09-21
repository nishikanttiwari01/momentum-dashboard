# Momentum Dashboard — Changelog

All notable changes to this project will be documented here.  
We follow a **phase-based versioning** (v0.x.0) where each phase corresponds to a locked milestone.

---
## v0.141.0 Phase 14: Enahncements (2025-09-22)

### Added
- **UI**
  - Revised momentum table with trading like look.
  - Revised right drawer. 
- **Backend Changes**
  - Introduced alerts via ntfy app.
  - Improved scoring and badge functions 

## v0.11.0 Phase 11: Indicators & Full Momentum Score (2025-09-15)

### Added
- **Indicators computation**
  - RSI(14), ADX(14) + slope, EMA(10/50/200), Relative Volume (20D), ATR%(14).
  - Returns over multiple windows: 1W, 1M, 3M, 6M, 12–1M.
  - 52-week high proximity with “📈 New High” badge trigger.
- **Momentum scoring**
  - Basic Score (0–12 scaled to %): RSI bands, ADX+slope, breakout quality, volume signals.
  - Full Score (0–100): P1 (Momentum), P2 (Breakout Quality), P3 (Accumulation & Volume), P4 (Market/Sector Context) with bonuses & penalties.
  - `score` column = `score_full` if available, else falls back to `score_basic`.
  - `score_scale = "0-100"` persisted for clarity.
- **Badges & recommendation**
  - Generated badges: e.g., “High Momentum”, “Very High Breakout”.
  - Recommendation + reason string (Yes/No with human-readable explanation).
- **Schema versioning**
  - Unified `scores/` dataset now written with `schema_version=2`.
  - All new columns persisted per-run alongside legacy fields.

### Changed
- **`screening_service.py`**
  - Writes enriched screener rows with `name`, `sector`, indicators, scores, badges, recommendation.
  - Persisted atomically with `_SUCCESS` marker and `rowcount.txt`.
- **`scores_repo.py`**
  - Collapsed v1/v2 logic into a single reader from `scores/` (schema v2).
  - Projection includes all Phase 11 columns; ensures `score` is always available.
  - Default sort now by `score.desc`.
- **API contract**
  - `/api/v1/screener` now returns the full momentum payload (indicators, scores, badges, recommendation).
  - `/api/v1/runs` and `/api/v1/scan` responses enriched with counts and snapshot path metadata.

### Fixed
- **Datetime serialization**
  - All run timestamps now timezone-aware and JSON serializable.
- **Rowcount tests**
  - Adjusted expectations: parquet snapshots now contain actual rows, not just empty “0” counters.

### Notes
- Phase 11 delivers the **full momentum screener backend**: all indicator fields, scoring logic, and recommendation reasoning are now persisted and queryable.
- Frontend changes will follow in Phase 12 to render these new fields; backend is feature-complete for momentum scoring.


## v0.10.0 Phase 10: Runs API, Idempotency & Hardening (2025-09-14)

### Added
- **Runs API**
  - `POST /api/v1/scan`: Start a manual screening run (idempotent). Returns `201 Created` on first run, `200 OK` on replay.
  - `GET /api/v1/runs`: List recent runs with optional status filter.
  - `GET /api/v1/runs/{run_id}`: Fetch details of a specific run.
- **Idempotency support**: `Idempotency-Key` header validation (1–64 chars, `[A-Za-z0-9_-]`).
- **SQLite Jobs Repo**: Store and retrieve run metadata (status, timings, counts).
- **Schema models**: Pydantic `RunSummary`, `RunDetail`, and `RunsList` for consistent API output.

### Changed
- **Alembic env**: Now respects `DB_URL` for test overrides; safer SQLite engine pooling for Windows.
- **Engine config**: Switched to `NullPool` to avoid file-lock issues in tests and migrations.
- **Screener contract**: Kept stable ahead of Indicators & Score work; default sorting remains unchanged.

### Fixed
- **Positions invariant**: Stop-loss updates are monotone non-decreasing and None-safe.
- **Idempotency tests**: POST routes now return `422` on bad key, `200` on replay (no duplicate jobs created).

### Tests
- Added coverage for:
  - Idempotency header validation.
  - Alembic migrations on temp DB.
  - Positions invariant enforcement.
  - Run list & detail API responses.

### Notes for Next Phase
- Phase 11 will implement **Indicators & Full Momentum Score**:
  - RSI/ADX/EMA, 12-1M/6M/3M/1M returns, relative volume, 52-week proximity, and badges.
  - Implement 0–100 scoring model.
  - Persist per-run outputs; Screener to show final computed columns.

## phase-9 - Manual scan but returning stubbed rows and write in data parquet folder (2025-09-13)
**Status:** Complete  
**Tag:** `phase-9`

### Added
- **Runs API**
  - `POST /api/v1/scan` — idempotent trigger using `Idempotency-Key` (`[A-Za-z0-9_-]{1,64}`).
  - `GET /api/v1/runs` — list recent runs.
  - `GET /api/v1/runs/{run_id}` — get a run by id (accepts `YYYYMMDDHHMMSS`; handler can normalize `YYYYMMDDTHHMMSSZ` if patch applied).
- **Job lifecycle (SQL)**
  - `jobs` table extended with `key` for idempotency.
  - Repo: `SqlJobsRepo.create_or_get_by_key(...)`, `complete_run(...)`, `fail_run(...)`, `list_recent(...)`.
- **Snapshot plumbing (Parquet)**
  - Atomic writer flow for `scores/` table partitions: `run_id=<id>/` with `_SUCCESS` and `rowcount.txt`.
  - Minimal writer path used by Phase 9 (writes an **empty** snapshot by design).
- **Service**
  - `screening_service.run_screening(...)` orchestrates idempotency → compute (stub) → snapshot → job complete.
- **Adapters scaffold**
  - `adapters/` package & NSE stub (`nse_adapter.py`) returning deterministic rows (kept disabled for tests).
- **Tests**
  - API + service tests for `/scan`, `/runs*`, idempotency semantics, and snapshot markers.

### Changed
- **Routers**
  - `api/v1/scan.py` and `api/v1/runs.py` mounted **once** by `main.py` using global API prefix (no duplicate `/api/v1` in routers).
- **DB session behavior**
  - Repos now **commit** after create/complete to make runs visible cross-request (fixes idempotent replays).
- **History repo**
  - Added `insert_run_summary(...)` as a no-op stub to satisfy service call sites.

### Fixed
- OpenAPI header component references for rate-limit headers (`Retry-After`, `X-RateLimit-*`).
- Idempotency response codes: **201** (first) / **200** (replay).
- Normalization pitfalls around `run_id` shape (API can accept both `YYYYMMDDHHMMSS` and `YYYYMMDDTHHMMSSZ` when normalization is enabled).

### Migrations
- `alembic/versions/20250912_0002_add_jobs_key.py` — adds `jobs.key` and indexes for lookup by `(name,key)` and by `run_id`.

### Notes / How to use
- **Trigger a run (Swagger):**
  - `POST /api/v1/scan` with header `Idempotency-Key: <your-key>`, empty body ok.
  - First call → **201** and snapshot path; same key → **200** (idempotent).
- **Verify snapshot on disk:**
  - `PARQUET_ROOT` (default `./backend/parquet`) → `scores/run_id=<id>/`
  - Expect `_SUCCESS` and `rowcount.txt` (Phase 9 writes `0` rows by design).
- **List & inspect runs:**
  - `GET /api/v1/runs?limit=20`
  - `GET /api/v1/runs/{run_id}`

### Breaking changes
- None (public APIs were introduced, not altered).

### Next (Phase 10 — Universe + Yahoo)
- CSV-driven **NSE universes** (`nifty50/100/500/all`) under `backend/data/universe/v1/`.
- `services/universe.py` to load/normalize symbols (→ `.NS`), precedence: request → config.
- `adapters/yahoo_adapter.py` with batching; `MARKET_SOURCE=yahoo` toggle in config.
- Update service to fetch real quotes and write **non-zero** snapshots; extend tests to mock Yahoo.


## 0.8.0 - Right Drawer Details (2025-09-12)
### Added
- **Endpoint:** `GET /api/v1/instruments/{symbol}/detail` returns the Drawer Detail payload.
- **Service layer:** `app/services/detail_service.py` to compose scores + indicators + positions + pins.
- **Domain logic:** `app/domain/meters.py` (risk/euphoria), `app/domain/next_action.py` (next_action, method pill).
- **Repos:**
  - `ScoresRepo.latest_run()` to resolve latest snapshot.
  - `ScoresRepo.read_one(symbol, run_id)` for single-row lookups.
  - `IndicatorsRepo.read_one(symbol, run_id)` minimal reader.
  - `PositionsRepo.get(symbol)` returns position dict incl. `entry_price_locked`, `qty`; derives `trade_on`.
  - `SnapshotPinsRepo.get(symbol)` returns pinned `run_id`.
- **Drawer fields:**
  - `position.entry_price`, `position.entry_price_locked`, `position.qty`, `position.trade_on`.
  - `meters.risk`, `meters.euphoria`.
  - `next_action.code`, `next_action.text`, `next_action.refs`, `method_pill`.
  - `badges[]` passthrough.
  - Trace fields: `run_id`, `as_of`, `symbol_canon`.
  - `score_total_0_100` (normalized score; `score` retained for back-compat).
- **Optional slice:** `GET /api/v1/instruments/{symbol}/sparkline` (returns empty list if dataset helper not present).

### Changed
- **OpenAPI (`contracts/openapi.yaml`):** Added DrawerDetail schema & `/instruments/{symbol}/detail` path; reused existing `NextAction` to avoid duplicates.
- **Routers:** `app/api/v1/instruments.py` (new) wired into `main.py`.
- **Error mapping:** Instruments route now returns `404 {detail: "Snapshot not found"}` when no run is available.

### Fixed
- None applicable.

### Notes
- **No DB migrations.** `trade_on` is derived from `qty > 0` when not stored.
- **Back-compat:** Kept existing imports working; `PositionsRepo` class accepts optional session.  
- **Frontend:** No changes required in Phase 8; endpoint is ready when FE implements the drawer.


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
