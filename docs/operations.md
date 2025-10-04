# Runbook & Operations

## Local Dev
- Python: `python -m venv .venv && source .venv/bin/activate` then `pip install -r backend/requirements.txt`
- API: `uvicorn app.main:app --reload --port 8000`
- Frontend: `pnpm i && pnpm dev` (or npm/yarn) with `VITE_API_BASE=http://localhost:8000/api/v1`
- DB init: ensure SQLite file path is writable; enable WAL; run migrations if present.
- Configs: base under `configs/` with environment overrides.

## Jobs & Scheduling
- Start APScheduler with app start; recurring **scan** job every 15m recommended.
- Each scan creates a `run_id` (UTC `YYYYMMDDHHmmss`), writes Parquet snapshot (atomic), updates `jobs` row with status, timings, rowcount.
- Post-scan: evaluate alert rules, update history, render email digest.

## Data Retention
- Keep intraday runs for 7d; daily 90d; weekly 6m; monthly 2y. Pin special `run_id`s before GC.

## Troubleshooting
- Parquet reads only after `_SUCCESS` marker; validate `rowcount.txt`.
- If drawers show `null` for 30d EMA arrays, verify market data fetch and alignment.
- For Windows file locks, prefer NullPool or ensure engine dispose on shutdown.