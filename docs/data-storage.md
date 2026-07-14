# Data & Storage

## Parquet Repositories

Detected Parquet-related modules:

- `app/repos/parquet/datasets.py`
- `app/repos/parquet/indicators_repo.py`
- `app/repos/parquet/scores_repo.py`
- `app/services/screening_service.py`
- `app/tools/parquet_smoke.py`
- `tests/test_parquet_datasets.py`
- `tests/api/test_scores_repo.py`
- `tests/api/test_screener_api.py`

## SQLite Tables (heuristic)

| Table | File | Columns (sample) |
|---|---|---|
| `alerts` | `app/repos/models.py` |  |
| `watchlist` | `app/repos/models.py` |  |
| `history` | `app/repos/models.py` |  |
| `jobs` | `app/repos/models.py` |  |
| `settings` | `app/repos/models.py` |  |
| `positions` | `app/repos/models.py` |  |
| `snapshot_pins` | `app/repos/models.py` |  |
| `alert_state` | `app/repos/sql/alerts_repo.py` | id, symbol, rule_code, last_score, last_fired_at_utc, last_fired_local_date, last_fired_run_id, id, run_id, symbol, rule_code, score, channels_sent_json, created_at_utc |
| `alert_events` | `app/repos/sql/alerts_repo.py` | id, symbol, rule_code, last_score, last_fired_at_utc, last_fired_local_date, last_fired_run_id, id, run_id, symbol, rule_code, score, channels_sent_json, created_at_utc |

## Config files

- `configs/default.yaml`
- `configs/development.yaml`
- `configs/prod-local.yaml`
- `configs/test.yaml`

## Scheduler & Notifications

**Schedulers (files containing APScheduler):**

- `app/core/config.py`
- `app/workers/scheduler.py`

**Notifications/Digests (by filename):**

- `app/notifs/email_digest.py`

# Wealth portfolio snapshots

Portfolio workbook imports use normalized SQLite records instead of rendering workbook cell positions directly.

- `portfolio_imports` stores the workbook fingerprint, safe basename, status, and issue counts. Workbook bytes and cell contents are not retained.
- `portfolio_snapshots` is an immutable dated view linked one-to-one with a successful import.
- `portfolio_assets`, `portfolio_transactions`, and `portfolio_valuations` store records scoped to a snapshot. Deterministic source keys prevent duplicates inside a snapshot while allowing the same historical transaction to appear in later immutable snapshots.
- `portfolio_fx_rates` stores dated currency rates and their provenance. Current totals use the latest applicable rate and expose when a cached fallback was required.

Upload previews live only in server memory for 30 minutes. Validation and preview do not write portfolio tables. Commit is atomic: any insert failure rolls back the import, snapshot, assets, transactions, and valuations together. Uploading identical workbook bytes returns the existing snapshot.

The importer recognizes current portfolio sheets but explicitly ignores `MF discont.`, `Property Cal.`, `REMIT`, and `STOCKS RECMDN`. Ignored-sheet cell values must not be opened, logged, persisted, or returned to the browser.

Backups of the application SQLite file include normalized portfolio snapshots and FX history, but not the source workbook. Retain the workbook separately if it is needed as an external source record.
