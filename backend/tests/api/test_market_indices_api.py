from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import market_indices
from app.services.market_index_service import (
    MarketIndexHistory,
    MarketIndexPoint,
    MarketIndexUnavailable,
)


class FakeService:
    def build_history(self, key: str, range_: str) -> MarketIndexHistory:
        if key not in {"sensex", "sp500"}:
            raise ValueError("unknown market index")
        if range_ == "5y":
            raise MarketIndexUnavailable("history unavailable")
        return MarketIndexHistory(
            key=key,
            name="Sensex",
            symbol="^BSESN",
            range=range_,
            latest_value=101.0,
            change=1.0,
            change_pct=1.0,
            points=[MarketIndexPoint(on=date(2026, 1, 2), close=101.0)],
        )


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(market_indices.router, prefix="/api/v1")
    app.dependency_overrides[market_indices.get_market_index_service] = FakeService
    return TestClient(app)


def test_market_index_history_returns_chart_ready_response():
    response = _client().get("/api/v1/market-indices/sensex/history?range=1y")

    assert response.status_code == 200
    assert response.json() == {
        "key": "sensex",
        "name": "Sensex",
        "symbol": "^BSESN",
        "range": "1y",
        "latest_value": 101.0,
        "change": 1.0,
        "change_pct": 1.0,
        "points": [{"on": "2026-01-02", "close": 101.0}],
    }


def test_market_index_history_returns_404_for_unknown_key():
    response = _client().get("/api/v1/market-indices/dow/history?range=1y")

    assert response.status_code == 404


def test_market_index_history_returns_422_for_invalid_range():
    response = _client().get("/api/v1/market-indices/sensex/history?range=10y")

    assert response.status_code == 422


def test_market_index_history_returns_503_when_upstream_is_unavailable():
    response = _client().get("/api/v1/market-indices/sensex/history?range=5y")

    assert response.status_code == 503
