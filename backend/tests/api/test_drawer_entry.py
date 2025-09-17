import pytest
from httpx import AsyncClient
from asgi_lifespan import LifespanManager

from app.api.v1 import instruments as instruments_api
from app.services.detail_service import DetailDeps

pytestmark = [pytest.mark.drawer, pytest.mark.drawer_entry]

class _ScoresStub:
    def __init__(self, latest=("RID_LATEST","2025-09-15T09:26:54Z"), rows=None, run_id="RID_LATEST"):
        self._latest = latest; self._rows = rows or {}; self._rid = run_id
    def latest_run(self): return self._latest
    def read_one(self, symbol, run_id): return self._rows.get(symbol) if run_id == self._rid else None

class _PositionsStub:
    def __init__(self, rows=None): self._rows = rows or {}
    def get(self, symbol): return self._rows.get(symbol)

class _PinsStub:
    def __init__(self, rid=None): self._rid = rid
    def get_pinned_run_id(self, symbol): return self._rid

def _deps(scores_row, *, run_id="RID_LATEST", positions_row=None, pinned=None, latest=("RID_LATEST","2025-09-15T09:26:54Z")):
    rows = {}
    if scores_row:
        rows[scores_row.get("symbol","TCS.NS")] = scores_row
    return DetailDeps(
        scores_repo=_ScoresStub(latest=latest, rows=rows, run_id=run_id),
        indicators_repo=None,
        positions_repo=_PositionsStub(rows={(positions_row or {}).get("symbol",""): positions_row}) if positions_row else _PositionsStub(),
        snapshot_pins_repo=_PinsStub(pinned)
    )

def _mk_row(symbol="XX.NS", last=100.0, ema8=None, ema10=98.0, ema50=95.0, ema200=90.0,
            rsi14=60.0, adx14=25.0, relvol20=1.0, prox52=-0.5, atr14_pct=2.0,
            change_pct=None, pct_today=None, score=55):
    row = {
        "symbol": symbol, "name": symbol, "sector": "", "last": last,
        "rsi14": rsi14, "adx14": adx14, "relvol20": relvol20, "proximity_52w_high_pct": prox52,
        "atr14_pct": atr14_pct, "score": score,
    }
    if ema8 is not None: row["ema8"] = ema8
    if ema10 is not None: row["ema10"] = ema10
    if ema50 is not None: row["ema50"] = ema50
    if ema200 is not None: row["ema200"] = ema200
    if pct_today is not None: row["pct_today"] = pct_today
    if change_pct is not None: row["change_pct"] = change_pct
    return row

@pytest.mark.asyncio
async def test_drawer_entry_breakout_when_unlocked(monkeypatch):
    symbol = "BRK.NS"
    row = _mk_row(symbol=symbol, last=110.0, ema10=100.0, rsi14=65.0, adx14=30.0, prox52=-0.2, atr14_pct=2.0)
    monkeypatch.setattr(instruments_api, "_deps", lambda: _deps(row))
    async with LifespanManager(instruments_api.app):
        async with AsyncClient(app=instruments_api.app, base_url="http://test") as ac:
            j = (await ac.get(f"/api/v1/instruments/{symbol}/detail")).json()
            assert j["position"]["entry_price"] == pytest.approx(110.0)
            assert j["next_action"]["refs"]["entry_type"] == "BREAKOUT"

@pytest.mark.asyncio
async def test_drawer_entry_pullback_band_when_extended(monkeypatch):
    symbol = "PULL.NS"
    row = _mk_row(symbol=symbol, last=110.0, ema8=105.0, ema10=100.0, rsi14=64.0, adx14=28.0, prox52=-0.4, atr14_pct=2.0)
    monkeypatch.setattr(instruments_api, "_deps", lambda: _deps(row))
    async with LifespanManager(instruments_api.app):
        async with AsyncClient(app=instruments_api.app, base_url="http://test") as ac:
            j = (await ac.get(f"/api/v1/instruments/{symbol}/detail")).json()
            assert j["next_action"]["refs"]["entry_type"] == "PULLBACK"
            assert j["next_action"]["refs"]["entry_high"] == pytest.approx(105.0)
            assert j["position"]["entry_price"] == pytest.approx(105.0)
            atr_abs = 110.0 * 0.02
            assert j["next_action"]["refs"]["entry_low"] == pytest.approx(105.0 - 0.5 * atr_abs, rel=1e-3)

@pytest.mark.asyncio
async def test_drawer_entry_starter_when_emerging(monkeypatch):
    symbol = "EMRG.NS"
    row = _mk_row(symbol=symbol, last=100.0, ema10=100.0, rsi14=56.0, adx14=21.0, prox52=-3.0, atr14_pct=2.0)
    monkeypatch.setattr(instruments_api, "_deps", lambda: _deps(row))
    async with LifespanManager(instruments_api.app):
        async with AsyncClient(app=instruments_api.app, base_url="http://test") as ac:
            j = (await ac.get(f"/api/v1/instruments/{symbol}/detail")).json()
            assert j["next_action"]["refs"]["entry_type"] == "STARTER"
            assert j["position"]["entry_price"] >= 100.0

@pytest.mark.asyncio
async def test_drawer_entry_watch_when_weak(monkeypatch):
    symbol = "WATCH.NS"
    row = _mk_row(symbol=symbol, last=95.0, ema10=100.0, rsi14=50.0, adx14=10.0, prox52=-10.0, atr14_pct=2.0)
    monkeypatch.setattr(instruments_api, "_deps", lambda: _deps(row))
    async with LifespanManager(instruments_api.app):
        async with AsyncClient(app=instruments_api.app, base_url="http://test") as ac:
            j = (await ac.get(f"/api/v1/instruments/{symbol}/detail")).json()
            assert j["next_action"]["refs"]["entry_type"] == "WATCH"
            assert j["position"]["entry_price"] == pytest.approx(95.0)

@pytest.mark.asyncio
async def test_drawer_entry_locked_overrides_suggestion(monkeypatch):
    symbol = "LOCK.NS"
    row = _mk_row(symbol=symbol, last=110.0, ema10=100.0, rsi14=65.0, adx14=30.0, prox52=-0.2)
    pos = {"symbol": symbol, "entry_price_locked": 97.5, "qty": 50, "trade_on": True}
    monkeypatch.setattr(instruments_api, "_deps", lambda: _deps(row, positions_row=pos))
    async with LifespanManager(instruments_api.app):
        async with AsyncClient(app=instruments_api.app, base_url="http://test") as ac:
            j = (await ac.get(f"/api/v1/instruments/{symbol}/detail")).json()
            assert j["position"]["entry_price"] == pytest.approx(97.5)
            assert j["position"]["entry_price_locked"] == pytest.approx(97.5)
