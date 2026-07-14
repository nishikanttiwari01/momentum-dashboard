from fastapi.testclient import TestClient

from app.main import app


def test_us_portfolio_routes_are_registered():
    paths = {route.path for route in app.routes}
    assert "/api/v1/portfolio/us/overview" in paths
    assert "/api/v1/portfolio/us/{instrument_id}/history" in paths
    assert "/api/v1/portfolio/us/transactions" in paths


def test_create_buy_rejects_zero_quantity():
    response = TestClient(app).post("/api/v1/portfolio/us/transactions", json={
        "instrument_id": "qqq",
        "purchased_at": "2026-07-01T14:30:00Z",
        "quantity": 0,
        "price_usd": 500,
        "fees_usd": 0,
    })
    assert response.status_code == 422
