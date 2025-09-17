import pytest
from httpx import AsyncClient
from asgi_lifespan import LifespanManager

from app.api.v1 import instruments as instruments_api
from app.services.detail_service import DetailDeps

pytestmark = [pytest.mark.drawer, pytest.mark.drawer_precedence]

class _ScoresStub:
    def __init__(self, rows, run_id):
        self.rows = rows; self.run_id=run_id
    def latest_run(self): return (self.run_id,"2025-09-15T09:26:54Z")
    def read_one(self, symbol, run_id): return self.rows.get(symbol) if run_id == self.run_id else None

class _PinsStub:
    def __init__(self, rid=None): self.rid=rid
    def get_pinned_run_id(self, s): return self.rid

def _deps(rows, *, run_id="RID_X", pinned=None):
    return DetailDeps(scores_repo=_ScoresStub(rows, run_id), indicators_repo=None, positions_repo=None, snapshot_pins_repo=_PinsStub(pinned))

def _row(sym="INFY.NS", **kw):
    base = dict(symbol=sym, name=sym, sector="", last=100.0, ema10=100.0, rsi14=60.0, adx14=25.0, relvol20=1.0)
    base.update(kw); return base

@pytest.mark.asyncio
async def test_drawer_precedence_explicit_over_pin_and_latest(monkeypatch):
    rows = {"INFY.NS": _row("INFY.NS")}
    monkeypatch.setattr(instruments_api, "_deps", lambda: _deps(rows, run_id="RID_LATEST", pinned="RID_PIN"))
    async with LifespanManager(instruments_api.app):
        async with AsyncClient(app=instruments_api.app, base_url="http://t") as ac:
            j = (await ac.get("/api/v1/instruments/INFY.NS/detail?run_id=RID_EXPL")).json()
            assert j["run_id"] == "RID_EXPL"

@pytest.mark.asyncio
async def test_drawer_precedence_pin_over_latest(monkeypatch):
    rows = {"INFY.NS": _row("INFY.NS")}
    monkeypatch.setattr(instruments_api, "_deps", lambda: _deps(rows, run_id="RID_LATEST", pinned="RID_PIN"))
    async with LifespanManager(instruments_api.app):
        async with AsyncClient(app=instruments_api.app, base_url="http://t") as ac:
            j = (await ac.get("/api/v1/instruments/INFY.NS/detail")).json()
            assert j["run_id"] == "RID_PIN"

@pytest.mark.asyncio
async def test_drawer_symbol_normalization_scores_and_positions(monkeypatch):
    rows = {"INFY.NS": _row("INFY.NS")}
    def deps():
        d = _deps(rows)
        class P:
            def get(self, s): return {"entry_price_locked": 97.0} if s in ("INFY","INFY.NS") else None
        d.positions_repo = P()
        return d
    monkeypatch.setattr(instruments_api, "_deps", deps)
    async with LifespanManager(instruments_api.app):
        async with AsyncClient(app=instruments_api.app, base_url="http://t") as ac:
            j = (await ac.get("/api/v1/instruments/INFY/detail")).json()
            assert j["position"]["entry_price"] == pytest.approx(97.0)
