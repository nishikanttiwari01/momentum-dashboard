# tests/api/test_screener_api.py
from __future__ import annotations
from datetime import date, datetime, timezone
from pathlib import Path
import math
from types import SimpleNamespace

import pyarrow as pa
import pytest
from fastapi.testclient import TestClient

from app.repos.parquet import datasets as ds
from app.repos.parquet import scores_repo
from app.repos.parquet.universe_repo import UniverseRepo
from app.main import create_app
from app.services.top_movers_service import ReturnRow


@pytest.fixture
def unified_top_movers_client(monkeypatch):
    from app.api.v1 import screener as screener_api

    rows = [
        {"symbol": "AAA", "name": "Alpha", "sector": "IT", "last": 101.0, "score": 80.0, "run_id": "run-1"},
        {"symbol": "BBB", "name": "Beta", "sector": "Energy", "last": 202.0, "score": 70.0, "run_id": "run-1"},
        {"symbol": "CCC", "name": "Gamma", "sector": "Finance", "last": 303.0, "score": 60.0, "run_id": "run-1"},
    ]

    class FakeRepo:
        calls = 0

        def read(self, **kwargs):
            self.calls += 1
            return rows, len(rows), "run-1", "2026-03-31T16:00:00Z"

    fake_repo = FakeRepo()
    monkeypatch.setattr(screener_api, "repo", fake_repo)
    monkeypatch.setattr(
        screener_api,
        "build_drawer_detail",
        lambda symbol, run_id, deps: {
            "next_action": {"code": "WATCH", "text": "Watch", "reasons": [], "refs": {}}
        },
    )
    monkeypatch.setattr(screener_api, "_get_detail_deps", lambda: object())
    calls = []

    def fake_load(symbols, start, end):
        calls.append((list(symbols), start, end))
        return [
            ReturnRow("AAA", 12.0, start, end),
            ReturnRow("CCC", 1.0, start, end),
            ReturnRow("BBB", -7.0, start, end),
        ]

    monkeypatch.setattr(screener_api, "load_and_rank_returns", fake_load, raising=False)
    return TestClient(create_app()), fake_repo, calls


@pytest.mark.parametrize(
    ("period", "expected_start"),
    [
        ("1d", date(2026, 3, 30)),
        ("1w", date(2026, 3, 24)),
        ("1m", date(2026, 2, 28)),
        ("3m", date(2025, 12, 31)),
        ("6m", date(2025, 9, 30)),
        ("1y", date(2025, 3, 31)),
        ("5y", date(2021, 3, 31)),
    ],
)
def test_unified_top_movers_supports_presets_relative_to_snapshot(
    unified_top_movers_client, period, expected_start
):
    client, fake_repo, calls = unified_top_movers_client

    response = client.get(f"/api/v1/screener/top-movers?period={period}")

    assert response.status_code == 200
    body = response.json()
    assert fake_repo.calls == 1
    assert calls[-1] == (["AAA", "BBB", "CCC"], expected_start, date(2026, 3, 31))
    assert [row["symbol"] for row in body["gainers"]] == ["AAA", "CCC", "BBB"]
    assert [row["symbol"] for row in body["losers"]] == ["BBB", "CCC", "AAA"]
    assert body["requested_start_date"] == expected_start.isoformat()
    assert body["requested_end_date"] == "2026-03-31"
    assert body["resolved_start_date"] == expected_start.isoformat()
    assert body["resolved_end_date"] == "2026-03-31"


def test_unified_top_movers_custom_range(unified_top_movers_client):
    client, _, calls = unified_top_movers_client

    response = client.get(
        "/api/v1/screener/top-movers?period=custom&start_date=2024-02-29&end_date=2025-02-28"
    )

    assert response.status_code == 200
    assert calls[-1][1:] == (date(2024, 2, 29), date(2025, 2, 28))
    body = response.json()
    assert body["requested_start_date"] == "2024-02-29"
    assert body["requested_end_date"] == "2025-02-28"


@pytest.mark.parametrize(
    ("query", "code"),
    [
        ("period=custom", "custom_dates_required"),
        ("period=custom&start_date=2026-02-01", "custom_dates_required"),
        ("period=custom&start_date=2026-02-02&end_date=2026-02-01", "invalid_date_range"),
        ("period=1m&start_date=2026-02-01", "custom_dates_not_allowed"),
        ("period=1m&end_date=2026-02-01", "custom_dates_not_allowed"),
    ],
)
def test_unified_top_movers_rejects_invalid_date_combinations(
    unified_top_movers_client, query, code
):
    client, _, _ = unified_top_movers_client
    response = client.get(f"/api/v1/screener/top-movers?{query}")
    assert response.status_code == 400
    assert response.json()["code"] == code
    assert response.json()["detail"]


def test_unified_top_movers_invalid_period_uses_fastapi_validation(unified_top_movers_client):
    client, _, _ = unified_top_movers_client
    response = client.get("/api/v1/screener/top-movers?period=2y")
    assert response.status_code == 422


def test_unified_top_movers_returns_no_trading_data(monkeypatch, unified_top_movers_client):
    from app.api.v1 import screener as screener_api

    client, _, _ = unified_top_movers_client
    monkeypatch.setattr(screener_api, "load_and_rank_returns", lambda *args: [], raising=False)
    response = client.get("/api/v1/screener/top-movers?period=1m")
    assert response.status_code == 400
    assert response.json()["code"] == "no_trading_data"
    assert response.json()["detail"] == "No stocks have usable trading data for the requested window."


def test_unified_top_movers_keeps_empty_eligible_result_distinct_from_no_data(
    monkeypatch, unified_top_movers_client
):
    from app.api.v1 import screener as screener_api

    eligibility = SimpleNamespace(
        enabled=True,
        min_price=0,
        min_avg_traded_value_cr=0,
        max_abs_change_pct=0,
    )
    monkeypatch.setattr(
        screener_api.app_config,
        "load",
        lambda: SimpleNamespace(
            screener=SimpleNamespace(top_movers=eligibility)
        ),
    )
    client, _, _ = unified_top_movers_client
    response = client.get("/api/v1/screener/top-movers?period=1m")
    assert response.status_code == 200
    assert response.json()["gainers"] == []
    assert response.json()["losers"] == []


def test_unified_top_movers_removes_old_top_performers_route(unified_top_movers_client):
    client, _, _ = unified_top_movers_client
    assert client.get("/api/v1/screener/top-performers").status_code == 404


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
        # kept in parquet so API can derive week fields
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
        # simple flags that may synthesize badges
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
    monkeypatch.setattr(scores_repo, "_ALLOW_LEGACY_FALLBACK", True)
    rid = _seed_scores(tmp_path)

    app = create_app()
    client = TestClient(app)

    # No params → latest snapshot
    r = client.get("/api/v1/screener")
    assert r.status_code == 200
    body = r.json()

    # envelope + trace
    assert body["pagination"]["total"] == 4
    assert body["run_id"] == rid
    assert isinstance(body["items"], list)

    # row shape
    row0 = body["items"][0]
    assert "symbol" in row0
    assert "wk_change" in row0
    assert "wk_change_pct" in row0
    assert isinstance(row0.get("badges", []), list)
    # internal parquet helper should not leak
    assert "ret_1w" not in row0

    # math sanity: wk_change ≈ last - last/(1 + pct/100)
    if row0["wk_change"] is not None and row0["wk_change_pct"] is not None:
        last = float(row0["last"])
        pct = float(row0["wk_change_pct"])
        base = last / (1.0 + pct / 100.0)
        expected = last - base
        assert math.isclose(row0["wk_change"], expected, rel_tol=1e-6, abs_tol=1e-6)

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


def test_screener_api_filters_by_universe(tmp_path, monkeypatch):
    monkeypatch.setenv("PARQUET_ROOT", str(tmp_path / "parquet"))
    monkeypatch.setattr(scores_repo, "_ALLOW_LEGACY_FALLBACK", True)
    _seed_scores(tmp_path, rows=4)

    preset_dir = tmp_path / "presets"
    preset_dir.mkdir(parents=True, exist_ok=True)
    (preset_dir / "NIFTY50.csv").write_text("SYM000\nSYM001\n", encoding="utf-8")
    (preset_dir / "SMALLCAP.csv").write_text("SYM999\n", encoding="utf-8")

    from app.api.v1 import screener as screener_api

    screener_api._universe_repo = UniverseRepo(assets_dir=preset_dir)
    screener_api._load_universe_symbols.cache_clear()

    app = create_app()
    client = TestClient(app)

    try:
        resp = client.get("/api/v1/screener?universe=NIFTY50")
        assert resp.status_code == 200
        body = resp.json()
        symbols = {item["symbol"] for item in body["items"]}
        assert symbols == {"SYM000", "SYM001"}
        assert body["pagination"]["total"] == 2

        resp2 = client.get("/api/v1/screener?universe=SMALLCAP")
        assert resp2.status_code == 200
        body2 = resp2.json()
        assert body2["items"] == []
        assert body2["pagination"]["total"] == 0
    finally:
        screener_api._universe_repo = None
        screener_api._load_universe_symbols.cache_clear()



def test_screener_api_filters_by_symbol(tmp_path, monkeypatch):
    monkeypatch.setenv("PARQUET_ROOT", str(tmp_path / "parquet"))
    monkeypatch.setattr(scores_repo, "_ALLOW_LEGACY_FALLBACK", True)
    _seed_scores(tmp_path, rows=4)

    app = create_app()
    client = TestClient(app)

    resp = client.get("/api/v1/screener?symbol=sym001")
    assert resp.status_code == 200
    body = resp.json()
    assert body["pagination"]["total"] == 1
    assert [item["symbol"] for item in body["items"]] == ["SYM001"]

    resp_missing = client.get("/api/v1/screener?symbol=ZZZ999")
    assert resp_missing.status_code == 200
    body_missing = resp_missing.json()
    assert body_missing["pagination"]["total"] == 0
    assert body_missing["items"] == []
