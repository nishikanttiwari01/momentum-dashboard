import pytest
from httpx import AsyncClient
from asgi_lifespan import LifespanManager

from app.api.v1 import instruments as instruments_api
from app.services.detail_service import DetailDeps

pytestmark = [pytest.mark.drawer, pytest.mark.drawer_next_action, pytest.mark.drawer_meters]

class _ScoresStub:
    def __init__(self, row, run_id="RIDX"):
        self.row=row; self.run_id=run_id
    def latest_run(self): return (self.run_id,"2025-09-15T09:26:54Z")
    def read_one(self, symbol, run_id): return self.row if run_id == self.run_id else None

def _deps(row):
    return DetailDeps(scores_repo=_ScoresStub(row), indicators_repo=None, positions_repo=None, snapshot_pins_repo=None)

def _row(**kw):
    base = dict(symbol="AAA.NS", name="AAA.NS", sector="", last=100.0, ema10=100.0, rsi14=60.0, adx14=25.0, relvol20=1.0)
    base.update(kw); return base

@pytest.mark.asyncio
async def test_drawer_next_action_hold_and_trail(monkeypatch):
    row = _row(last=102.0, ema10=100.0)
    def deps():
        d = _deps(row)
        class P: 
            def get(self, s): return {"entry_price_locked": 98.0, "stop_now": 99.5}
        d.positions_repo = P()
        return d
    monkeypatch.setattr(instruments_api, "_deps", deps)
    async with LifespanManager(instruments_api.app):
        async with AsyncClient(app=instruments_api.app, base_url="http://t") as ac:
            j = (await ac.get("/api/v1/instruments/AAA.NS/detail")).json()
            assert j["next_action"]["code"] in ("HOLD_TRAIL", "HOLD")
            if j["next_action"]["code"] == "HOLD_TRAIL":
                assert "trail stop" in j["next_action"]["text"]

@pytest.mark.asyncio
async def test_drawer_risk_euphoria_buckets(monkeypatch):
    row = _row(relvol20=0.9, rsi14=58.0, adx14=20.0)
    monkeypatch.setattr(instruments_api, "_deps", lambda: _deps(row))
    async with LifespanManager(instruments_api.app):
        async with AsyncClient(app=instruments_api.app, base_url="http://t") as ac:
            j = (await ac.get("/api/v1/instruments/AAA.NS/detail")).json()
            assert j["meters"]["risk"]["level"] in ("Low","Medium","High")
            assert j["meters"]["euphoria"]["level"] in ("Low","Medium","High")
