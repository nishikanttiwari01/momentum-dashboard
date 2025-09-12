# tests/repos/test_scores_repo.py
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pytest

from app.repos.parquet import datasets as ds
from app.repos.parquet.scores_repo import ScoresRepo


def _seed_scores(tmp_root: Path, run_id: str = "20250912T100000Z", rows: int = 6):
    (tmp_root / "parquet").mkdir(parents=True, exist_ok=True)
    symbols = [f"SYM{i:03d}" for i in range(rows)]
    data = {
        "symbol": symbols,
        "name": [f"Name {i}" for i in range(rows)],
        "sector": ["Energy", "Energy", "Financials", "IT", "IT", "Energy"][:rows],
        "last": [100.0 + i for i in range(rows)],
        "change_pct": [0.1 * i for i in range(rows)],
        "score": [90, 80, 70, 60, 50, 40][:rows],
        "strength": ["Strong", "Strong", "Moderate", "Moderate", "Weak", "Weak"][:rows],
        "rsi": [65, 60, 55, 50, 45, 40][:rows],
        "adx": [25, 22, 18, 15, 12, 10][:rows],
        "ret_12_1m": [15.0]*rows,
        "ret_6m": [10.0]*rows,
        "ret_3m": [6.0]*rows,
        "ret_1m": [2.0]*rows,
        "ret_1w": [0.5, 0.4, 0.3, 0.2, 0.1, -0.1][:rows],
        "pct_from_52w_high": [-4.0]*rows,
        "atr_pct": [2.0]*rows,
        "liquidity": [1.5e8]*rows,
        "vol_spike": [1.3]*rows,
        "pct_today": [0.8]*rows,
        "buy": [False]*rows,
        "reason": [""]*rows,
        "source": ["scan"]*rows,
        "stale": [False]*rows,
        "run_id": [run_id]*rows,
        "as_of": [datetime.now(timezone.utc).isoformat().replace("+00:00","Z")]*rows,
        "last_index": ["2025-09-01"]*rows,
        # boolean hints for badges
        "breakout": [True, False, False, True, False, False][:rows],
        "near_uc":  [False, True, False, False, False, True][:rows],
    }
    tab = pa.table(data)
    ds.write_schema_version("scores", 1)
    w = ds.begin_atomic_write("scores", run_id)
    w.write_df(tab)
    w.commit()
    return run_id


def test_read_filters_sort_pagination(tmp_path, monkeypatch):
    monkeypatch.setenv("PARQUET_ROOT", str(tmp_path / "parquet"))
    rid = _seed_scores(tmp_path)

    repo = ScoresRepo()
    # Filter: sector in Energy/IT and score >= 60
    items, total, resolved_run_id, _ = repo.read(
        run_id=rid,
        as_of_str=None,
        filters={("sector", "in"): ["Energy", "IT"], ("score", "gte"): 60},
        sort="score.desc,last.desc",
        page=1,
        per_page=10,
        columns=["symbol","sector","score","last","badges","run_id","as_of","ret_1w"],
    )

    assert total >= 1
    assert resolved_run_id == rid
    # sorted by score desc
    scores = [r["score"] for r in items]
    assert scores == sorted(scores, reverse=True)
    # badges synthesized from booleans
    assert all(isinstance(r.get("badges"), list) for r in items)
    # ret_1w present
    assert "ret_1w" in items[0]

    # Pagination check: page 2 with per_page=2 using the SAME filters
    items2, total2, _, _ = repo.read(
        run_id=rid,
        as_of_str=None,
        filters={("sector", "in"): ["Energy", "IT"], ("score", "gte"): 60},  # <-- keep filters
        sort="score.desc",
        page=2,
        per_page=2,
        columns=["symbol", "score", "badges"],
    )
    assert total2 == total
    assert len(items2) <= 2


def test_empty_when_no_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("PARQUET_ROOT", str(tmp_path / "parquet"))
    repo = ScoresRepo()
    items, total, rid, asof = repo.read(
        run_id=None, as_of_str=None, filters={}, sort="score.desc", page=1, per_page=50, columns=["symbol"]
    )
    assert items == []
    assert total == 0
    assert rid is None
    assert asof is None
