# backend/tests/e2e/test_seed_to_api.py
from __future__ import annotations
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from app.repos.value_objects import AlertRuleVO 

from app.core.db import init_sqlite, get_sessionmaker
from app.main import create_app
from app.repos.unit_of_work import SqliteUnitOfWork


def test_seed_to_api_edge_isolated(tmp_path: Path, monkeypatch):
    # 1) Create a temp DB path under pytest's temp dir
    db_path = tmp_path / "e2e.sqlite"
    db_url = f"sqlite:///{db_path}"

    # 2) Point the app to the temp DB (env var drives get_settings())
    monkeypatch.setenv("APP_SQLITE_PATH", str(db_path))

    # 3) Run Alembic migrations programmatically against the temp DB
    backend_dir = Path(__file__).resolve().parents[2]  # .../backend
    alembic_ini = backend_dir / "alembic.ini"
    cfg = Config(str(alembic_ini))
    cfg.set_main_option("sqlalchemy.url", db_url)  # <-- critical: target temp DB
    command.upgrade(cfg, "head")

    # 4) Seed *through* the UoW on the temp DB (no global state)
    init_sqlite(str(db_path))
    uow = SqliteUnitOfWork(get_sessionmaker())
    with uow:
        uow.watchlist.upsert_symbol("RELIANCE")
        uow.alerts.create_alert(
            AlertRuleVO(
                id=None,
                symbol="RELIANCE",
                rule_type="price_crosses",
                rule_value="3000",
                channels=["desktop"],
                enabled=True,
                created_at=None,
                updated_at=None,
            )
        ) # if your repo expects VO, call constructor there

    # 5) Spin up the FastAPI app; it will read APP_SQLITE_PATH and use the temp DB
    app = create_app()
    client = TestClient(app)

    # 6) Read via API edge
    r = client.get("/api/v1/alerts")
    assert r.status_code == 200, r.text
    symbols = {a["rule"]["symbol"] for a in r.json()}
    assert "RELIANCE" in symbols

    # 7) Write via API edge and verify round-trip
    r2 = client.post("/api/v1/alerts", json={
        "symbol": "INFY",
        "rule_type": "price_crosses",
        "rule_value": "1600",
        "channels": ["desktop"],
        "enabled": True
    })
    assert r2.status_code in (200, 201), r2.text
    assert r2.json()["rule"]["symbol"] == "INFY"

    r3 = client.get("/api/v1/alerts")
    assert any(a["rule"]["symbol"] == "INFY" for a in r3.json())
