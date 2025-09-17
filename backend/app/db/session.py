# app/db/session.py
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

_ENGINE = None
_SessionLocal: Optional[sessionmaker] = None

def init_sqlite(db_path: Optional[str] = None) -> None:
    """
    Initialize the SQLite engine once. Safe to call multiple times.
    """
    global _ENGINE, _SessionLocal
    if _ENGINE is not None and _SessionLocal is not None:
        return
    # Default location (match your existing config if different)
    db_path = db_path or str(Path.cwd() / "data" / "app.db")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{db_path}"
    _ENGINE = create_engine(url, connect_args={"check_same_thread": False})
    _SessionLocal = sessionmaker(bind=_ENGINE, autocommit=False, autoflush=False)


def _ensure():
    if _ENGINE is None or _SessionLocal is None:
        # Lazily initialize to make tests resilient when lifespan isn't entered
        init_sqlite()

@contextmanager
def get_session() -> Iterator[Session]:
    _ensure()
    assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

def get_sessionmaker() -> sessionmaker:
    _ensure()
    assert _SessionLocal is not None
    return _SessionLocal
