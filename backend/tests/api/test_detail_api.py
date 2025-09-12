# tests/api/test_detail_api.py
from __future__ import annotations
from typing import Optional, Any
from fastapi.testclient import TestClient

from app.main import create_app
from app.api.v1 import instruments as instruments_api
from app.services.detail_service import DetailDeps


# --- Stub repos for isolated API tests (no real DB/Parquet needed) ---

class StubScoresRepo:
    def __init__(self, row: dict, latest: tuple[Optional[str], Optional[str]] = ("RID_LATEST", None)) -> None:
        self._row = row
        self._latest = latest

    def latest_run(self) -> tuple[Optional[str], Optional[str]]:
        return self._latest

    def read_one(self, *, symbol: str, run_id: str) -> dict | None:
        # Return a copy to avoid mutation across tests
        return {**self._row, "symbol": symbol, "run_id": run_id}


class StubIndicatorsRepo:
    def __init__(self, row: dict) -> None:
        self._row = row

    def read_one(self, *, symbol: str, run_id: str) -> dict | None:
        return {**self._row, "symbol": symbol, "run_id": run_id}


class StubPositionsRepo:
    def __init__(self, row: dict | None) -> None:
        self._row = row

    def get(self, symbol: str) -> dict | None:
        return None if self._row is None else dict(self._row)


class StubPinsRepo:
    def __init__(self, pinned: Optional[str] = None) -> None:
        self._pinned = pinned

    def get(self, symbol: str) -> Optional[str]:
        return self._pinned


def _deps(scores_row: dict, ind_row: dict, pos_row: dict | None, latest: tuple[Optional[str], Optional[str]] = ("RID_LATEST", None), pinned: Optional[str] = None) -> DetailDeps:
    return DetailDeps(
        scores=StubScoresRepo(scores_row, latest),
        indicators=StubIndicatorsRepo(ind_row),
        positions=StubPositionsRepo(pos_row),
        pins=StubPinsRepo(pinned),
    )


# ---------------------------- Tests ----------------------------

def test_detail_happy_path(monkeypatch):
    """
    run_id provided → service uses it (no need for pin/latest).
    Asserts presence and shape of drawer payload.
    """
    symbol = "TCS.NS"
    run_id = "RID_20250911_153000"

    scores_row = {
        "name": "Tata Consultancy Services",
        "sector": "IT Services",
        "last": 4012.50,
        "change_pct": 1.24,         # service falls back to this if pct_today missing
        "score": 0.82,
        "badges": [
            {"code": "very_high_breakout", "text": "Very High Breakout"},
            {"code": "high_momentum", "text": "High Momentum"},
        ],
        "proximity_52w_high_pct": 0.7,
        "atr_pct": 2.1,             # used by risk meter
    }
    ind_row = {
        "rsi14": 68.4,
        "adx14": 32.1,
        "adx_slope": 0.9,
        "ema_fast": 8, "ema_fast_value": 3950.3,
        "ema_slow": 10, "ema_slow_value": 3928.7,
        "relvol20": 1.8,
    }
    pos_row = {
        "entry_price": 3840.0,
        "entry_price_locked": 3820.0,
        "qty": 50,
        "trade_on": True,
        "stop_now": 3925.0,
        "exit_close_threshold": 3901.5,
        "breakeven_active": True,
        "euphoria_on": False,
        "note": None,
    }

    # Monkeypatch dependency factory to return our stubs
    monkeypatch.setattr(instruments_api, "_deps", lambda: _deps(scores_row, ind_row, pos_row))

    app = create_app()
    client = TestClient(app)

    resp = client.get(f"/api/v1/instruments/{symbol}/detail", params={"run_id": run_id})
    assert resp.status_code == 200
    body = resp.json()

    # Top-level fields
    assert body["run_id"] == run_id
    assert body["symbol"] == symbol
    assert body["name"] == "Tata Consultancy Services"
    assert body["sector"] == "IT Services"
    assert body["price"] == 4012.50
    assert body["score"] == 0.82

    # Indicators & badges
    assert "indicators" in body and isinstance(body["indicators"], dict)
    assert body["indicators"]["rsi14"] == 68.4
    assert len(body.get("badges", [])) == 2

    # Position block (includes new fields)
    pos = body["position"]
    assert pos["entry_price"] == 3840.0
    assert pos["entry_price_locked"] == 3820.0
    assert pos["qty"] == 50
    assert pos["trade_on"] is True

    # Meters exist
    assert body["meters"]["risk"]["level"] in ("Low", "Medium", "High")
    assert "next_action" in body and "code" in body["next_action"]


def test_detail_uses_pinned_run_when_no_query_param(monkeypatch):
    """
    No run_id in query and a pin exists → service uses pinned run_id.
    """
    symbol = "RELIANCE.NS"
    pinned_run = "RID_PINNED"

    scores_row = {"name": "Reliance", "sector": "Energy", "last": 2700.5, "change_pct": 1.2, "score": 0.78, "atr_pct": 2.0}
    ind_row = {"rsi14": 60.0, "adx14": 20.0, "ema_slow": 10, "ema_slow_value": 2680.0}

    monkeypatch.setattr(instruments_api, "_deps", lambda: _deps(scores_row, ind_row, pos_row=None, latest=("RID_LATEST", None), pinned=pinned_run))

    app = create_app()
    client = TestClient(app)

    resp = client.get(f"/api/v1/instruments/{symbol}/detail")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == pinned_run


def test_detail_404_when_no_snapshot_available(monkeypatch):
    """
    No run_id in query, no pin, and latest_run() is empty → 404.
    """
    symbol = "INFY.NS"
    scores_row = {}  # won't be reached
    ind_row = {}

    # latest_run returns (None, None) and no pin
    monkeypatch.setattr(instruments_api, "_deps", lambda: _deps(scores_row, ind_row, pos_row=None, latest=(None, None), pinned=None))

    app = create_app()
    client = TestClient(app)

    resp = client.get(f"/api/v1/instruments/{symbol}/detail")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Snapshot not found"
