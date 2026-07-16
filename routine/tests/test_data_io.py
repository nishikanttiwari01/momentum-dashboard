"""data_io against a temp parquet lake with schema evolution + quirks."""
from __future__ import annotations

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from routine import data_io


@pytest.fixture
def lake(tmp_path):
    root = tmp_path / "scores" / "daily"

    def write(day: str, run_id: str, df: pd.DataFrame):
        d = root / f"as_of={day}" / f"run_id={run_id}"
        d.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pandas(df), d / "part-00000.parquet")

    # old-schema day (no pre_breakout_score)
    write("2025-01-01", "r1", pd.DataFrame({"symbol": ["aaa", "BBB"], "close": [10.0, 20.0]}))
    # day with two runs — later run must win
    write("2025-01-02", "r1", pd.DataFrame({"symbol": ["AAA"], "close": [99.0], "pre_breakout_score": [1]}))
    write("2025-01-02", "r2", pd.DataFrame({"symbol": ["AAA"], "close": [11.0], "pre_breakout_score": [15]}))
    # empty partition (holiday) — must be skipped
    (root / "as_of=2025-01-03").mkdir(parents=True)
    # duplicate symbol within one file — keep last
    write("2025-01-06", "r1", pd.DataFrame({"symbol": ["AAA", "AAA"], "close": [12.0, 12.5]}))
    return root


def test_list_snapshot_dates_skips_empty(lake):
    assert data_io.list_snapshot_dates(root=lake) == ["2025-01-01", "2025-01-02", "2025-01-06"]


def test_load_snapshot_missing_columns_filled(lake):
    df = data_io.load_snapshot("2025-01-01", columns=["symbol", "close", "pre_breakout_score"], root=lake)
    assert list(df.columns)[:3] == ["symbol", "close", "pre_breakout_score"]
    assert df["pre_breakout_score"].isna().all()


def test_load_snapshot_latest_run_wins(lake):
    df = data_io.load_snapshot("2025-01-02", columns=["symbol", "close", "pre_breakout_score"], root=lake)
    assert df["close"].iloc[0] == 11.0
    assert df["pre_breakout_score"].iloc[0] == 15


def test_panel_uppercases_and_dedupes(lake):
    panel = data_io.load_feature_panel(columns=["symbol", "close"], root=lake)
    assert set(panel["symbol"]) == {"AAA", "BBB"}
    d6 = panel[(panel["as_of"] == "2025-01-06") & (panel["symbol"] == "AAA")]
    assert len(d6) == 1 and d6["close"].iloc[0] == 12.5


def test_close_matrix_shape(lake):
    panel = data_io.load_feature_panel(columns=["symbol", "close"], root=lake)
    m = data_io.close_matrix(panel)
    assert list(m.index) == ["2025-01-01", "2025-01-02", "2025-01-06"]
    assert m.loc["2025-01-01", "AAA"] == 10.0
