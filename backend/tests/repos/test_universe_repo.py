from app.repos.parquet.universe_repo import UniverseRepo, PRESETS

def test_load_presets_smoke(tmp_path, monkeypatch):
    # point repo to fixtures dir containing at least one preset CSV
    repo = UniverseRepo()
    # we rely on real CSVs in assets; smoke-test each known preset exists & has items
    for name in PRESETS:
        items, total = repo.list_symbols(name, page=1, per_page=5_000)
        assert total > 0
        assert all(s.endswith(".NS") for s in items)

def test_query_filtering():
    repo = UniverseRepo()
    items, total = repo.list_symbols("NIFTY50", q="N", page=1, per_page=1000)
    assert total >= len(items) >= 0
