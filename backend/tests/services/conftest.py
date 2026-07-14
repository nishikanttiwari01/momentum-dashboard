from pathlib import Path

import pytest

from app.core.db import dispose_engine, get_sessionmaker, init_sqlite


@pytest.fixture
def session(tmp_path: Path):
    dispose_engine()
    init_sqlite(str(tmp_path / "wealth-service.db"))
    db = get_sessionmaker()()
    try:
        yield db
    finally:
        db.close()
        dispose_engine()
