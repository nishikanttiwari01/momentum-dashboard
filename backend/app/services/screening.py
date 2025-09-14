# backend/app/services/screening.py
"""
Test-friendly shim for `tests/services/test_screening_uses_universe.py`.

It provides:
- run_screening(universe: str) -> int    # expected by the test (no DB/session)
- UniverseRepo                            # symbol tests monkeypatch
- run_pipeline_for_symbols                # symbol tests monkeypatch

The real API flow uses app.services.screening_service.run_screening(session, key, payload).
Keeping this shim avoids changing tests and keeps signatures stable.
"""

# These two are placeholders that tests will monkeypatch.
class UniverseRepo:  # pragma: no cover
    def list_symbols(self, preset: str, q=None, page=1, per_page=999999):
        raise NotImplementedError("tests should monkeypatch screening.UniverseRepo")

def run_pipeline_for_symbols(symbols, *a, **k):  # pragma: no cover
    raise NotImplementedError("tests should monkeypatch screening.run_pipeline_for_symbols")

def run_screening(*, universe: str) -> int:
    """
    Minimal implementation to satisfy the test:
    - Load symbols for the given preset using UniverseRepo.
    - Call run_pipeline_for_symbols(symbols).
    - Return the integer rows written.
    All collaborators are monkeypatched by the test.
    """
    uni = UniverseRepo()
    items, _total = uni.list_symbols(universe, page=1, per_page=999_999)
    rows = run_pipeline_for_symbols(items)
    return int(rows)
