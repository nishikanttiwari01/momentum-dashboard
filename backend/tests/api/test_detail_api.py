import pytest
from asgi_lifespan import LifespanManager
from httpx import AsyncClient, ASGITransport
import app.api.v1.instruments as instruments_api

def _deps(scores_row, ind_row, pos_row=None, latest=("RID_LATEST", None), pinned=None):
    class _Scores:
        def latest_run(self): return latest
        def read_one(self, *, symbol, run_id): return {**scores_row, **ind_row} if run_id else None
    class _Pins:
        def get_pinned_run_id(self, symbol): return pinned
    class _Pos:
        def get(self, symbol): return pos_row
    return instruments_api.DetailDeps(
        scores_repo=_Scores(),
        indicators_repo=None,
        positions_repo=_Pos() if pos_row else None,
        snapshot_pins_repo=_Pins() if pinned is not None else None,
    )

@pytest.mark.asyncio
async def test_detail_happy_path(monkeypatch):
    symbol = "TCS.NS"
    scores_row = {"name": "TCS", "sector": "IT", "last": 4012.5, "change_pct": 1.2, "score": 0.82}
    ind_row = {"rsi14": 68.4, "adx14": 32.1, "ema_fast": 8, "ema_fast_value": 3950.3, "ema_slow": 10, "ema_slow_value": 3928.7, "relvol20": 1.8}
    pos_row = {"entry_price": 3840.0, "entry_price_locked": 3820.0, "stop_now": 3925.0, "exit_close_threshold": 3901.5, "breakeven_active": True, "euphoria_on": False}
    monkeypatch.setattr(instruments_api, "_deps", lambda: _deps(scores_row, ind_row, pos_row))
    async with LifespanManager(instruments_api.app):
        transport = ASGITransport(app=instruments_api.app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get(f"/api/v1/instruments/{symbol}/detail", params={"run_id": "RID_20250911_153000"})
            assert r.status_code == 200
            body = r.json()
            assert body["symbol"] == symbol
            assert "meters" in body and "next_action" in body

@pytest.mark.asyncio
async def test_detail_uses_pinned_run_when_no_query_param(monkeypatch):
    symbol = "RELIANCE.NS"
    scores_row = {"name": "Reliance", "sector": "Energy", "last": 2700.5, "change_pct": 1.2, "score": 0.78}
    ind_row = {"rsi14": 60.0, "adx14": 20.0, "ema_slow": 10, "ema_slow_value": 2680.0}
    monkeypatch.setattr(instruments_api, "_deps",
                        lambda: _deps(scores_row, ind_row, pos_row=None, latest=("RID_LATEST", None), pinned="RID_PINNED"))
    async with LifespanManager(instruments_api.app):
        transport = ASGITransport(app=instruments_api.app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get(f"/api/v1/instruments/{symbol}/detail")
            assert r.status_code == 200
            assert r.json()["run_id"] == "RID_PINNED"

@pytest.mark.asyncio
async def test_detail_404_when_no_snapshot_available(monkeypatch):
    symbol = "INFY.NS"
    monkeypatch.setattr(instruments_api, "_deps",
                        lambda: _deps(scores_row={}, ind_row={}, pos_row=None, latest=(None, None), pinned=None))
    async with LifespanManager(instruments_api.app):
        transport = ASGITransport(app=instruments_api.app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get(f"/api/v1/instruments/{symbol}/detail")
            assert r.status_code == 404
