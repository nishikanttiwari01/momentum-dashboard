# tests/conftest.py
from __future__ import annotations

import os
from pathlib import Path
import sys
import pytest

try:
    from fastapi.testclient import TestClient  # type: ignore
except Exception:  # pragma: no cover
    TestClient = None  # type: ignore

# Ensure backend/ is importable (keep your original shim)
backend_dir = Path(__file__).resolve().parents[1]  # .../backend
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Use the real app (lifespan calls init_sqlite and disposes engine on shutdown)
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client() -> TestClient:
    if TestClient is None:
        pytest.skip('fastapi.testclient/httpx not available')
    with TestClient(app) as c:
        yield c


@pytest.fixture
def tmp_parquet_root(monkeypatch, tmp_path: Path):
    """
    Override PARQUET_ROOT so Phase-9 snapshot writes (_SUCCESS, rowcount.txt)
    land in a temporary, per-test directory.
    """
    prev = os.environ.get("PARQUET_ROOT")
    os.environ["PARQUET_ROOT"] = str(tmp_path)
    try:
        yield tmp_path
    finally:
        if prev is None:
            os.environ.pop("PARQUET_ROOT", None)
        else:
            os.environ["PARQUET_ROOT"] = prev
