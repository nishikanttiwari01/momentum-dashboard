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