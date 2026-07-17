from datetime import date

import pyarrow as pa
import pytest

from app.services.top_movers_service import (
    ReturnRow,
    load_and_rank_returns,
    rank_returns,
    resolve_window,
)


def _prices(rows):
    return pa.Table.from_pylist(rows)


def test_resolve_window_uses_a_true_trailing_calendar_year():
    assert resolve_window("1y", date(2024, 2, 29)) == (
        date(2023, 2, 28),
        date(2024, 2, 29),
    )


def test_resolve_window_supports_standard_periods_and_custom_boundaries():
    end = date(2026, 7, 17)

    assert resolve_window("1d", end) == (date(2026, 7, 16), end)
    assert resolve_window("1w", end) == (date(2026, 7, 10), end)
    assert resolve_window("1m", end) == (date(2026, 6, 17), end)
    assert resolve_window("3m", end) == (date(2026, 4, 17), end)
    assert resolve_window("6m", end) == (date(2026, 1, 17), end)
    assert resolve_window("5y", end) == (date(2021, 7, 17), end)
    assert resolve_window(
        "custom",
        end,
        start_date=date(2025, 1, 2),
        end_date=date(2025, 3, 4),
    ) == (date(2025, 1, 2), date(2025, 3, 4))


def test_rank_returns_uses_first_and_last_trading_days_inside_boundaries():
    table = _prices(
        [
            {"symbol": "AAA", "dt": "2026-01-02", "close": 90.0, "adj_close": None},
            {"symbol": "AAA", "dt": "2026-01-05", "close": 100.0, "adj_close": None},
            {"symbol": "AAA", "dt": "2026-01-09", "close": 110.0, "adj_close": None},
            {"symbol": "AAA", "dt": "2026-01-12", "close": 120.0, "adj_close": None},
        ]
    )

    assert rank_returns(table, ["AAA"], date(2026, 1, 3), date(2026, 1, 11)) == [
        ReturnRow("AAA", pytest.approx(10.0), date(2026, 1, 5), date(2026, 1, 9))
    ]


def test_rank_returns_can_use_latest_two_sessions_for_daily_movers():
    table = _prices(
        [
            {"symbol": "AAA", "dt": "2026-03-20", "close": 80.0},
            {"symbol": "AAA", "dt": "2026-03-27", "close": 100.0},
            {"symbol": "AAA", "dt": "2026-03-30", "close": 105.0},
        ]
    )

    assert rank_returns(
        table,
        ["AAA"],
        date(2026, 3, 20),
        date(2026, 3, 30),
        latest_two=True,
    ) == [
        ReturnRow("AAA", pytest.approx(5.0), date(2026, 3, 27), date(2026, 3, 30))
    ]


def test_rank_returns_prefers_adjusted_close_and_falls_back_per_row():
    table = _prices(
        [
            {"symbol": "ADJ", "dt": date(2026, 1, 2), "close": 100.0, "adj_close": 50.0},
            {"symbol": "ADJ", "dt": date(2026, 1, 3), "close": 120.0, "adj_close": 60.0},
            {"symbol": "FALL", "dt": date(2026, 1, 2), "close": 80.0, "adj_close": None},
            {"symbol": "FALL", "dt": date(2026, 1, 3), "close": 100.0, "adj_close": float("nan")},
        ]
    )

    rows = rank_returns(table, ["ADJ", "FALL"], date(2026, 1, 2), date(2026, 1, 3))

    assert rows == [
        ReturnRow("FALL", pytest.approx(25.0), date(2026, 1, 2), date(2026, 1, 3)),
        ReturnRow("ADJ", pytest.approx(20.0), date(2026, 1, 2), date(2026, 1, 3)),
    ]


def test_rank_returns_omits_missing_history_and_zero_start():
    table = _prices(
        [
            {"symbol": "ONE", "dt": "2026-01-02", "close": 10.0},
            {"symbol": "ZERO", "dt": "2026-01-02", "close": 0.0},
            {"symbol": "ZERO", "dt": "2026-01-03", "close": 10.0},
            {"symbol": "OK", "dt": "2026-01-02", "close": 10.0},
            {"symbol": "OK", "dt": "2026-01-03", "close": 11.0},
        ]
    )

    assert [row.symbol for row in rank_returns(
        table, ["ONE", "ZERO", "OK", "ABSENT"], date(2026, 1, 2), date(2026, 1, 3)
    )] == ["OK"]


def test_rank_returns_breaks_equal_return_ties_by_symbol():
    table = _prices(
        [
            {"symbol": symbol, "dt": day, "close": price}
            for symbol in ("ZZZ", "AAA")
            for day, price in (("2026-01-02", 10.0), ("2026-01-03", 11.0))
        ]
    )

    rows = rank_returns(table, ["ZZZ", "AAA"], date(2026, 1, 2), date(2026, 1, 3))

    assert [row.symbol for row in rows] == ["AAA", "ZZZ"]


def test_load_and_rank_returns_scans_once_and_tolerates_missing_adj_close(monkeypatch):
    table = _prices(
        [
            {"symbol": "AAA", "dt": "2026-01-02", "close": 10.0},
            {"symbol": "AAA", "dt": "2026-01-03", "close": 11.0},
        ]
    )
    calls = []

    def fake_scan(*args, **kwargs):
        calls.append((args, kwargs))
        return table

    monkeypatch.setattr("app.services.top_movers_service.datasets.scan", fake_scan)

    rows = load_and_rank_returns(["AAA"], date(2026, 1, 2), date(2026, 1, 3))

    assert [row.symbol for row in rows] == ["AAA"]
    assert calls == [
        (("prices",), {
            "run_id": None,
            "dt_range": ("2026-01-02", "2026-01-03"),
            "columns": ["symbol", "dt", "close", "adj_close"],
        })
    ]


def test_load_and_rank_returns_retries_without_adj_close_for_legacy_schema(monkeypatch):
    table = _prices(
        [
            {"symbol": "AAA", "dt": "2026-01-02", "close": 10.0},
            {"symbol": "AAA", "dt": "2026-01-03", "close": 11.0},
        ]
    )
    calls = []

    def fake_scan(*args, **kwargs):
        calls.append((args, kwargs))
        if "adj_close" in kwargs["columns"]:
            raise pa.ArrowInvalid("No match for FieldRef.Name(adj_close)")
        return table

    monkeypatch.setattr("app.services.top_movers_service.datasets.scan", fake_scan)

    rows = load_and_rank_returns(["AAA"], date(2026, 1, 2), date(2026, 1, 3))

    assert [row.symbol for row in rows] == ["AAA"]
    assert [call[1]["columns"] for call in calls] == [
        ["symbol", "dt", "close", "adj_close"],
        ["symbol", "dt", "close"],
    ]


def test_load_and_rank_returns_does_not_swallow_unrelated_arrow_errors(monkeypatch):
    def fake_scan(*_args, **_kwargs):
        raise pa.ArrowInvalid("Failed parsing partition expression")

    monkeypatch.setattr("app.services.top_movers_service.datasets.scan", fake_scan)

    with pytest.raises(pa.ArrowInvalid, match="partition expression"):
        load_and_rank_returns(["AAA"], date(2026, 1, 2), date(2026, 1, 3))
