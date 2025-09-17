import pytest
from app.services import detail_service as svc
from app.services.detail_service import DetailDeps

pytestmark = [pytest.mark.drawer, pytest.mark.drawer_logging]

class _ScoresStub:
    def __init__(self, row, run_id="RID_LOG"): self.row=row; self.run_id=run_id
    def latest_run(self): return (self.run_id, "2025-09-15T09:26:54Z")
    def read_one(self, symbol, run_id): return self.row if run_id == self.run_id else None

def _row():
    return dict(symbol="LOGS.NS", last=100.0, ema10=100.0, rsi14=60.0, adx14=25.0, relvol20=1.0)

def _deps():
    return DetailDeps(scores_repo=_ScoresStub(_row()), indicators_repo=None, positions_repo=None, snapshot_pins_repo=None)

def test_drawer_builder_emits_key_logs(caplog, monkeypatch):
    caplog.set_level("INFO", logger="app.services.detail")
    payload = svc.build_drawer_detail("LOGS.NS", "RID_LOG", _deps())
    msgs = " ".join(r.message for r in caplog.records if r.name == "app.services.detail")
    assert "ema_map" in msgs
    assert "positions lookup keys tried" in msgs
    assert "entry_suggestion" in msgs
    assert payload["symbol"] == "LOGS.NS"
