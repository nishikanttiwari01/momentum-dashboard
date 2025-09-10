from __future__ import annotations
from fastapi.testclient import TestClient
from app.core.db import init_sqlite
from app.main import create_app  # assumes your factory exists


def test_post_get_alerts():
    init_sqlite("./data/test_api.db")
    app = create_app()
    client = TestClient(app)

    # POST
    r = client.post("/api/v1/alerts", json={
        "symbol": "INFY",
        "rule_type": "price_crosses",
        "rule_value": "1600",
        "channels": ["desktop"],
        "enabled": True
    })
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["symbol"] == "INFY"

    # GET
    r = client.get("/api/v1/alerts")
    assert r.status_code == 200
    arr = r.json()
    assert any(a["symbol"] == "INFY" for a in arr)
