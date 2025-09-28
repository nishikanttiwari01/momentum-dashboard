import numpy as np
import pandas as pd

from app.core.db import get_sessionmaker
from app.services import screening_service

def test_run_screening_uses_preset(monkeypatch, tmp_parquet_root):
    captured = {}

    class FakeUniverseRepo:
        def list_symbols(self, preset, q=None, page=1, per_page=999_999):
            captured["preset"] = preset
            return (["RELIANCE.NS", "TCS.NS"], 2)

    class FakeYahooAdapter:
        def fetch_quotes(self, symbols):
            return [{"symbol": s, "name": f"Name {s}", "sector": "Tech"} for s in symbols]

    def fake_history_df(symbol: str, period: str = "400d"):
        idx = pd.date_range(end=pd.Timestamp.today(), periods=160, freq="B")
        base = np.linspace(100.0, 130.0, len(idx))
        data = {
            "open": base + 0.5,
            "high": base + 1.0,
            "low": base - 1.0,
            "close": base,
            "volume": np.full(len(idx), 1_000_000.0),
            "adj_close": base,
        }
        return pd.DataFrame(data, index=idx)

    monkeypatch.setattr(screening_service, "UniverseRepo", lambda *a, **k: FakeUniverseRepo())
    monkeypatch.setattr(screening_service, "YahooAdapter", lambda: FakeYahooAdapter())
    monkeypatch.setattr(screening_service, "_history_df", fake_history_df)

    sm = get_sessionmaker()
    with sm() as session:
        detail, created = screening_service.run_screening(session=session, key="TEST_U1", payload={})

    assert created is True
    assert detail.run_id
    assert captured.get("preset") == "ALL"
    assert detail.snapshot_path
    assert detail.counts.rows_written >= 0
