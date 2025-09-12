# tests/api/test_screener_api.py
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
from fastapi.testclient import TestClient

from app.repos.parquet import datasets as ds
from app.main import create_app


def _seed_scores(tmp_root: Path, run_id: str = "20250912T101500Z", rows: int = 4):
    (tmp_root / "parquet").mkdir(parents=True, exist_ok=True)
    data = {
        "symbol": [f"SYM{i:03d}" for i in range(rows)],
        "name": [f"Name {i}" for i in range(rows)],
        "sector": ["Energy", "IT", "Energy", "Financials"][:rows],
        "last": [100.0 + i for i in range(rows)],
        "change_pct": [0.1 * i for i in range(rows)],
        "score": [80, 70, 60, 50][:rows],
        "strength": ["Strong", "Moderate", "Moderate", "Weak"][:rows],
        "rsi": [62, 58, 52, 48][:rows],
        "adx": [22, 18, 16, 14][:rows],
        "ret_12_1m": [15.0]*rows,
        "ret_6m": [10.0]*rows,
        "ret_3m": [6.0]*rows,
        "ret_1m": [2.0]*rows,
        "ret_1w": [0.5, 0.4, 0.2, 0.1][:rows],
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
        "breakout": [True, False, False, False][:rows],
        "near_uc":  [False, True,  False, False][:rows],
    }
    tab = pa.table(data)
    ds.write_schema_version("scores", 1)
    w = ds.begin_atomic_write("scores", run_id)
    w.write_df(tab)
    w.commit()
    return run_id


def test_screener_api_happy_path(tmp_path, monkeypatch):
    # Isolate to temp parquet root
    monkeypatch.setenv("PARQUET_ROOT", str(tmp_path / "parquet"))
    rid = _seed_scores(tmp_path)

    app = create_app()
    client = TestClient(app)

    # No params → latest snapshot
    r = client.get("/api/v1/screener")
    assert r.status_code == 200
    body = r.json()
    assert body["pagination"]["total"] == 4
    assert body["run_id"] == rid
    assert isinstance(body["items"], list)
    assert "symbol" in body["items"][0]
    assert "ret_1w" in body["items"][0]
    assert isinstance(body["items"][0]["badges"], list)

    # Filters + sort + page
    r2 = client.get("/api/v1/screener?sector.in=Energy&score.gte=60&sort=score.desc&page=1&per_page=1")
    assert r2.status_code == 200
    b2 = r2.json()
    assert b2["pagination"]["per_page"] == 1
    assert len(b2["items"]) <= 1
    if b2["items"]:
        assert b2["items"][0]["sector"] == "Energy"

    # Direct run id
    r3 = client.get(f"/api/v1/screener?run_id={rid}")
    assert r3.status_code == 200


def test_screener_api_empty_when_no_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("PARQUET_ROOT", str(tmp_path / "parquet"))
    app = create_app()
    client = TestClient(app)
    r = client.get("/api/v1/screener")
    assert r.status_code == 200
    b = r.json()
    assert b["items"] == []
    assert b["pagination"]["total"] == 0
