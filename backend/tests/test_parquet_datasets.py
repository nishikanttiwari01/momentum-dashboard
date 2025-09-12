# tests/test_parquet_datasets.py
from __future__ import annotations

import os
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from app.repos.parquet import datasets as ds


def _set_tmp_root(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "parquet"
    monkeypatch.setenv("PARQUET_ROOT", str(root))
    return root


def test_atomic_write_and_scan_roundtrip(tmp_path, monkeypatch):
    _set_tmp_root(tmp_path, monkeypatch)

    run_id = "20250912T040000Z"
    # ensure schema version exists (also gets mirrored into file metadata)
    ds.write_schema_version("scores", 1)

    w = ds.begin_atomic_write("scores", run_id)
    tab = pa.table(
        {
            "symbol": ["AAA", "BBB"],
            "name": ["Name A", "Name B"],
            "sector": ["Energy", "Financials"],
            "last": [101.0, 202.0],
            "change_pct": [0.5, -0.2],
            "score": [77, 64],
            "strength": ["Moderate", "Weak"],
            "run_id": [run_id, run_id],
            "as_of": ["2025-09-12T04:00:00Z", "2025-09-12T04:00:00Z"],
        }
    )
    w.write_df(tab)
    w.commit()

    # latest snapshot resolves correctly
    latest = ds.latest_snapshot("scores")
    assert latest == run_id

    # markers present
    part_dir = (tmp_path / "parquet" / "scores" / f"run_id={run_id}")
    assert (part_dir / "_SUCCESS").exists()
    assert (part_dir / "rowcount.txt").read_text().strip() == "2"

    # read back
    out = ds.scan("scores", run_id=latest)
    assert out.num_rows == 2
    assert set(out.column_names) >= {"symbol", "score", "strength"}

    # parquet file metadata includes run_id and schema_version
    parts = sorted(p for p in part_dir.iterdir() if p.name.startswith("part-") and p.suffix == ".parquet")
    assert parts, "expected at least one part-*.parquet"
    md = pq.read_metadata(parts[0]).metadata or {}
    assert md.get(b"run_id") == run_id.encode()
    assert md.get(b"schema_version") == b"1"


def test_abort_removes_temp_dir(tmp_path, monkeypatch):
    root = _set_tmp_root(tmp_path, monkeypatch)
    run_id = "20250912T040500Z"

    w = ds.begin_atomic_write("scores", run_id)
    tab = pa.table({"symbol": ["X"], "score": [1]})
    w.write_df(tab)

    # temp dir exists before abort
    assert w.tmp_dir.exists()
    w.abort()
    # temp dir is gone after abort
    assert not w.tmp_dir.exists()
    # final partition must not exist
    assert not (root / "scores" / f"run_id={run_id}").exists()


def test_latest_snapshot_none_when_empty(tmp_path, monkeypatch):
    _set_tmp_root(tmp_path, monkeypatch)
    assert ds.latest_snapshot("scores") is None


def test_schema_version_read_write(tmp_path, monkeypatch):
    _set_tmp_root(tmp_path, monkeypatch)
    assert ds.read_schema_version("scores") is None
    ds.write_schema_version("scores", 3)
    assert ds.read_schema_version("scores") == 3


@pytest.mark.parametrize(
    "rid",
    [
        "20250912040500",      # YYYYMMDDHHMMSS
        "20250912T040500Z",    # YYYYMMDDTHHMMSSZ
    ],
)
def test_begin_atomic_write_accepts_both_run_id_forms(tmp_path, monkeypatch, rid):
    _set_tmp_root(tmp_path, monkeypatch)
    w = ds.begin_atomic_write("scores", rid)
    w.write_df(pa.table({"symbol": ["S"], "score": [42]}))
    w.commit()
    assert ds.latest_snapshot("scores") == rid
