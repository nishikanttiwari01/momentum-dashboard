from datetime import date

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from app.services.score_snapshot_history import (
    load_score_snapshot_returns,
    resolve_snapshot_dates,
)
from app.services.top_movers_service import ReturnRow


def _write_snapshot(root, as_of, run_id, rows, *, filename="part.parquet"):
    target = root / "scores" / "daily" / f"as_of={as_of}" / f"run_id={run_id}"
    target.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), target / filename)


def test_resolve_snapshot_dates_shortens_start_to_earliest_archive(tmp_path):
    daily = tmp_path / "daily"
    for name in ("as_of=2024-01-02", "as_of=2025-01-02", "as_of=2026-01-02"):
        (daily / name).mkdir(parents=True)

    assert resolve_snapshot_dates(
        daily, date(2021, 1, 1), date(2025, 12, 31), latest_two=False
    ) == (date(2024, 1, 2), date(2025, 1, 2))


def test_resolve_snapshot_dates_uses_first_archive_date_on_or_after_custom_start(tmp_path):
    daily = tmp_path / "daily"
    for name in ("as_of=2024-01-02", "as_of=2024-02-01", "as_of=2024-03-01"):
        (daily / name).mkdir(parents=True)

    assert resolve_snapshot_dates(
        daily, date(2024, 1, 15), date(2024, 3, 15), latest_two=False
    ) == (date(2024, 2, 1), date(2024, 3, 1))


def test_resolve_snapshot_dates_latest_two_ignores_start_and_uses_last_two(tmp_path):
    daily = tmp_path / "daily"
    for name in ("as_of=2024-01-02", "as_of=2024-02-01", "as_of=2024-03-01"):
        (daily / name).mkdir(parents=True)

    assert resolve_snapshot_dates(
        daily, date(2024, 3, 1), date(2024, 3, 15), latest_two=True
    ) == (date(2024, 2, 1), date(2024, 3, 1))


def test_resolve_snapshot_dates_requires_two_distinct_dates_and_ignores_malformed_dirs(tmp_path):
    daily = tmp_path / "daily"
    for name in (
        "as_of=2024-02-30",
        "as_of=2024-01-02-extra",
        "as_of=not-a-date",
        "date=2024-01-01",
        "as_of=2024-01-02",
        "as_of=2025-01-01",
    ):
        (daily / name).mkdir(parents=True)

    assert resolve_snapshot_dates(
        daily, date(2020, 1, 1), date(2024, 12, 31), latest_two=False
    ) is None


def test_load_score_snapshot_returns_reads_boundaries_and_newest_run(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.services.score_snapshot_history.datasets.get_parquet_root", lambda: tmp_path
    )
    _write_snapshot(
        tmp_path,
        "2024-01-02",
        "20240102T090000Z",
        [{"symbol": "AAA", "last": 25.0}],
    )
    _write_snapshot(
        tmp_path,
        "2024-01-02",
        "20240102T100000Z",
        [{"symbol": "AAA", "last": 100.0}],
    )
    _write_snapshot(
        tmp_path,
        "2024-03-01",
        "20240301T100000Z",
        [{"symbol": "AAA", "last": 150.0}],
    )

    assert load_score_snapshot_returns(
        ["AAA"], date(2020, 1, 1), date(2024, 3, 15)
    ) == [ReturnRow("AAA", pytest.approx(50.0), date(2024, 1, 2), date(2024, 3, 1))]


def test_load_score_snapshot_returns_prefers_last_and_falls_back_to_close_per_row(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "app.services.score_snapshot_history.datasets.get_parquet_root", lambda: tmp_path
    )
    _write_snapshot(
        tmp_path,
        "2024-01-02",
        "one",
        [
            {"symbol": "PREFER", "last": 100.0, "close": 10.0, "as_of": "2024-01-02"},
            {"symbol": "FALL", "last": None, "close": 80.0, "as_of": "2024-01-02"},
        ],
    )
    _write_snapshot(
        tmp_path,
        "2024-01-03",
        "two",
        [
            {"symbol": "PREFER", "last": 110.0, "close": 30.0, "as_of": "2024-01-03"},
            {"symbol": "FALL", "last": None, "close": 100.0, "as_of": "2024-01-03"},
        ],
    )

    rows = load_score_snapshot_returns(
        ["PREFER", "FALL"], date(2024, 1, 1), date(2024, 1, 3), latest_two=True
    )

    assert rows == [
        ReturnRow("FALL", pytest.approx(25.0), date(2024, 1, 2), date(2024, 1, 3)),
        ReturnRow("PREFER", pytest.approx(10.0), date(2024, 1, 2), date(2024, 1, 3)),
    ]


@pytest.mark.parametrize(
    "invalid_last", [0.0, -1.0, float("nan"), float("inf"), "not-a-price"]
)
def test_load_score_snapshot_returns_rejects_present_invalid_last(
    tmp_path, monkeypatch, invalid_last
):
    monkeypatch.setattr(
        "app.services.score_snapshot_history.datasets.get_parquet_root", lambda: tmp_path
    )
    valid_last = "100.0" if isinstance(invalid_last, str) else 100.0
    _write_snapshot(
        tmp_path,
        "2024-01-02",
        "one",
        [{"symbol": "BAD", "last": valid_last, "close": 100.0}],
    )
    _write_snapshot(
        tmp_path,
        "2024-01-03",
        "two",
        [{"symbol": "BAD", "last": invalid_last, "close": 110.0}],
    )

    assert load_score_snapshot_returns(
        ["BAD"], date(2024, 1, 2), date(2024, 1, 3)
    ) == []


def test_load_score_snapshot_returns_requires_symbol_at_both_boundaries(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.services.score_snapshot_history.datasets.get_parquet_root", lambda: tmp_path
    )
    _write_snapshot(tmp_path, "2024-01-02", "one", [{"symbol": "AAA", "last": 100.0}])
    _write_snapshot(tmp_path, "2024-01-03", "two", [{"symbol": "OTHER", "last": 110.0}])

    assert load_score_snapshot_returns(
        ["AAA"], date(2024, 1, 2), date(2024, 1, 3)
    ) == []


def test_load_score_snapshot_returns_handles_schema_drift_across_boundary_files(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "app.services.score_snapshot_history.datasets.get_parquet_root", lambda: tmp_path
    )
    _write_snapshot(tmp_path, "2024-01-02", "one", [{"symbol": "AAA", "close": 100.0}])
    _write_snapshot(tmp_path, "2024-01-03", "two", [{"symbol": "AAA", "last": 150.0}])

    assert load_score_snapshot_returns(
        ["AAA"], date(2024, 1, 2), date(2024, 1, 3)
    ) == [ReturnRow("AAA", pytest.approx(50.0), date(2024, 1, 2), date(2024, 1, 3))]
