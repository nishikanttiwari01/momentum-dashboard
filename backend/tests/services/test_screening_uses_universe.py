from app.services import screening

def test_run_screening_uses_preset(monkeypatch):
    # monkeypatch UniverseRepo to assert it's called with our preset and returns a tiny set
    class FakeUni:
        def list_symbols(self, preset, q=None, page=1, per_page=999999):
            assert preset == "NIFTY50"
            return (["RELIANCE.NS","TCS.NS"], 2)
    monkeypatch.setattr(screening, "UniverseRepo", lambda *a, **k: FakeUni())
    # monkeypatch adapter to capture symbols
    captured = {}
    def fake_pipeline(symbols, *a, **k):
        captured["symbols"] = list(symbols)
        return 2  # rows written
    monkeypatch.setattr(screening, "run_pipeline_for_symbols", fake_pipeline)
    rows = screening.run_screening(universe="NIFTY50")
    assert rows == 2
    assert set(captured["symbols"]) == {"RELIANCE.NS","TCS.NS"}
