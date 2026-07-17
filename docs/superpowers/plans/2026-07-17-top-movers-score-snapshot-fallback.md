# Top Movers Score-Snapshot Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Top Movers return usable results from archived daily score snapshots when the dedicated prices Parquet dataset is empty.

**Architecture:** Add a focused score-snapshot history reader that resolves actual archive boundaries and returns the same `ReturnRow` objects as the prices reader. `load_and_rank_returns` keeps prices as the preferred source and invokes the snapshot reader only when prices produce no usable returns; the API and frontend contract remain unchanged.

**Tech Stack:** Python 3.11, FastAPI, PyArrow/Parquet, pytest, existing daily score archive.

---

## File structure

- Create `backend/app/services/score_snapshot_history.py`: discover daily score partitions, select honest boundary snapshots, batch-read symbol closes, and calculate fallback returns.
- Create `backend/tests/services/test_score_snapshot_history.py`: unit tests for date resolution, shortened history, snapshot prices, and invalid rows.
- Modify `backend/app/services/top_movers_service.py`: prefer price results, then invoke the snapshot fallback.
- Modify `backend/tests/services/test_top_movers_service.py`: source-priority and empty-source orchestration tests.
- Modify `backend/tests/api/test_screener_api.py`: production regression for an empty prices dataset plus current score snapshots.

### Task 1: Add the score-snapshot history reader

**Files:**
- Create: `backend/app/services/score_snapshot_history.py`
- Create: `backend/tests/services/test_score_snapshot_history.py`

- [ ] **Step 1: Write failing snapshot-boundary tests**

Create temporary partitions matching production, for example `scores/daily/as_of=2024-08-23/run_id=20240824010000/part-00000.parquet`, and assert:

```python
def test_resolve_snapshot_dates_shortens_range_to_available_history(tmp_path):
    write_snapshot(tmp_path, "2024-08-23", {"AAA": 100.0})
    write_snapshot(tmp_path, "2026-07-16", {"AAA": 150.0})
    assert resolve_snapshot_dates(
        tmp_path / "scores" / "daily",
        date(2021, 7, 16),
        date(2026, 7, 16),
        latest_two=False,
    ) == (date(2024, 8, 23), date(2026, 7, 16))
```

Add separate tests proving `latest_two=True` selects the two latest archive dates at or before the requested end, a start within history selects the first snapshot on or after it, and fewer than two distinct dates returns `None`.

- [ ] **Step 2: Run the new test file and verify RED**

Run: `python -m pytest backend/tests/services/test_score_snapshot_history.py -q`

Expected: collection fails because `app.services.score_snapshot_history` does not exist.

- [ ] **Step 3: Implement deterministic partition resolution**

Define:

```python
def resolve_snapshot_dates(
    daily_root: Path,
    requested_start: date,
    requested_end: date,
    *,
    latest_two: bool,
) -> tuple[date, date] | None:
```

Parse only directories named `as_of=YYYY-MM-DD`, ignore malformed/future partitions, sort unique dates, and select two distinct boundaries. For `latest_two`, select the last two dates not after `requested_end`. Otherwise select the first available date on or after `requested_start`, falling back to the archive's earliest date when the request predates it, plus the last date not after `requested_end`.

- [ ] **Step 4: Write failing return-row tests**

Use snapshots containing `symbol`, `last`, `close`, and `as_of`. Assert a 100-to-150 close produces `ReturnRow("AAA", 50.0, ...)`, `last` is preferred with row-level `close` fallback only when missing, and zero/negative/non-finite prices or symbols missing from either boundary are omitted.

- [ ] **Step 5: Implement the batch snapshot reader**

Define:

```python
def load_score_snapshot_returns(
    symbols: Iterable[str],
    requested_start: date,
    requested_end: date,
    *,
    latest_two: bool = False,
) -> list[ReturnRow]:
```

Resolve the two boundary dates, select the newest `run_id=*` directory under each boundary, create one PyArrow dataset from the selected Parquet files, read only `symbol`, `last`, `close`, and `as_of`, convert records into a small table with `symbol`, `dt`, and `close`, and call the existing `rank_returns`. Do not call Yahoo or another network provider.

- [ ] **Step 6: Run snapshot tests and existing service tests**

Run: `python -m pytest backend/tests/services/test_score_snapshot_history.py backend/tests/services/test_top_movers_service.py -q`

Expected: all tests pass.

- [ ] **Step 7: Commit the reader**

```powershell
git add backend/app/services/score_snapshot_history.py backend/tests/services/test_score_snapshot_history.py
git commit -m "feat: read mover returns from score snapshots"
```

### Task 2: Add price-first fallback orchestration and API regression coverage

**Files:**
- Modify: `backend/app/services/top_movers_service.py`
- Modify: `backend/tests/services/test_top_movers_service.py`
- Modify: `backend/tests/api/test_screener_api.py`

- [ ] **Step 1: Write failing source-priority tests**

Monkeypatch the prices scan and snapshot loader. Assert non-empty price returns are returned without calling snapshots; an empty price table calls snapshots once with identical symbols/window/latest-two mode; and both empty sources return an empty list.

```python
def test_empty_prices_fall_back_to_score_snapshots(monkeypatch):
    monkeypatch.setattr(datasets, "scan", lambda *args, **kwargs: pa.table({"symbol": [], "dt": [], "close": []}))
    expected = [ReturnRow("AAA", 10.0, date(2026, 7, 15), date(2026, 7, 16))]
    monkeypatch.setattr(snapshot_history, "load_score_snapshot_returns", lambda *args, **kwargs: expected)
    assert load_and_rank_returns({"AAA"}, date(2021, 7, 16), date(2026, 7, 16), latest_two=True) == expected
```

- [ ] **Step 2: Run the orchestration tests and verify RED**

Run: `python -m pytest backend/tests/services/test_top_movers_service.py -q`

Expected: fallback tests fail because empty price results are returned directly.

- [ ] **Step 3: Implement price-first fallback**

In `load_and_rank_returns`, keep the existing single prices scan and ranking path. Return immediately when it produces rows. Otherwise call `load_score_snapshot_returns(symbols, start, end, latest_two=latest_two)` and return its rows. Convert `symbols` to a tuple once so both readers receive the same universe when the caller supplied a generator.

- [ ] **Step 4: Add the production-shaped API regression test**

Seed current screener rows, leave `<PARQUET_ROOT>/prices` empty, and write two real score partitions with known closes. Call `/api/v1/screener/top-movers?period=5y` and assert HTTP 200, ranked movers, `requested_start_date` earlier than the archive, and `resolved_start_date` equal to the earliest seeded snapshot.

- [ ] **Step 5: Run focused backend verification**

Run:

```powershell
python -m pytest backend/tests/services/test_score_snapshot_history.py backend/tests/services/test_top_movers_service.py -q
python -m pytest backend/tests/api/test_screener_api.py -k "top_movers or top_performers" -q
```

Expected: both commands pass; the two unrelated generic screener baseline failures remain excluded.

- [ ] **Step 6: Reproduce the live endpoint successfully**

With the local backend running, run:

`curl.exe -i http://127.0.0.1:8000/api/v1/screener/top-movers?period=1d`

Expected: HTTP 200 with non-empty `gainers`/`losers` and resolved dates drawn from the local score archive. Restart the backend first if it does not auto-reload Python changes.

- [ ] **Step 7: Commit orchestration and regression coverage**

```powershell
git add backend/app/services/top_movers_service.py backend/tests/services/test_top_movers_service.py backend/tests/api/test_screener_api.py
git commit -m "fix: fall back to score snapshots for movers"
```

### Task 3: Final verification

**Files:**
- Modify only if a new fallback regression is reproduced with a failing test first.

- [ ] **Step 1: Run all focused feature tests**

Run: `python -m pytest backend/tests/services/test_score_snapshot_history.py backend/tests/services/test_top_movers_service.py backend/tests/api/test_screener_api.py -k "snapshot or top_movers or top_performers" -q`

Expected: all selected tests pass.

- [ ] **Step 2: Verify unchanged frontend compatibility**

Run from `frontend`: `node_modules\.bin\vitest.cmd run src/pages/DashboardPage.top-movers.test.tsx`

Expected: all Top Movers UI tests pass without frontend changes.

- [ ] **Step 3: Check scope and worktree state**

Run:

```powershell
git diff --check
git status --short
git log -5 --oneline
```

Expected: no whitespace errors, only intended fallback files are committed, and the working tree is clean.
