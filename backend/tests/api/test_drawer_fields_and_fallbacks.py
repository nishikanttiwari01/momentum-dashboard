import pytest
from httpx import AsyncClient
from asgi_lifespan import LifespanManager

from app.api.v1 import instruments as instruments_api
from app.services.detail_service import DetailDeps

pytestmark = [pytest.mark.drawer, pytest.mark.drawer_fields]

class _ScoresStub:
    def __init__(self, row, run_id="RID_F"): self.row=row; self.run_id=run_id
    def latest_run(self): return (self.run_id,"2025-09-15T09:26:54Z")
    def read_one(self, symbol, run_id): return self.row if run_id == self.run_id else None

def _deps(row):
    return DetailDeps(scores_repo=_ScoresStub(row), indicators_repo=None, positions_repo=None, snapshot_pins_repo=None)

def _row(**kw):
    base = dict(symbol="FALL.NS", name="FALL.NS", sector="X", last=123.45, ema10=120.0, rsi14=55.0, adx14=20.0, relvol20=0.9, score=17)
    base.update(kw); return base

@pytest.mark.asyncio
async def test_drawer_pct_today_falls_back_to_change_pct(monkeypatch):
    row = _row(change_pct=1.23)  # pct_today missing
    monkeypatch.setattr(instruments_api, "_deps", lambda: _deps(row))
    async with LifespanManager(instruments_api.app):
        async with AsyncClient(app=instruments_api.app, base_url="http://t") as ac:
            j = (await ac.get("/api/v1/instruments/FALL.NS/detail")).json()
            assert j["pct_today"] == pytest.approx(1.23)

@pytest.mark.asyncio
async def test_drawer_channels_null_and_badges_default_empty(monkeypatch):
    row = _row()
    monkeypatch.setattr(instruments_api, "_deps", lambda: _deps(row))
    async with LifespanManager(instruments_api.app):
        async with AsyncClient(app=instruments_api.app, base_url="http://t") as ac:
            j = (await ac.get("/api/v1/instruments/FALL.NS/detail")).json()
            assert j["channels"] is None
            assert isinstance(j["badges"], list)
