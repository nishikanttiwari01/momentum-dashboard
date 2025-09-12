from __future__ import annotations

from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool  # <-- add

from alembic.config import Config as AlembicConfig
from alembic import command as alembic_command

from .config import get_settings
from ..repos.models import Base

_engine = None
_SessionLocal: Optional[sessionmaker] = None
_current_db_url: Optional[str] = None

def _alembic_upgrade_head(sqlite_path: str) -> None:
    backend_dir = Path(__file__).resolve().parents[2]
    cfg = AlembicConfig(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{Path(sqlite_path)}")
    alembic_command.upgrade(cfg, "head")

def init_sqlite(db_path: str | None = None):
    cfg = get_settings()
    path = db_path or cfg.storage.sqlite_path
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    _alembic_upgrade_head(path)

    global _engine, _SessionLocal, _current_db_url
    url = f"sqlite:///{path}"
    if _engine is None or _current_db_url != url:
        _engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=NullPool,          # <-- important on Windows
            pool_pre_ping=True,
            future=True,
        )
        with _engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
            conn.exec_driver_sql("PRAGMA foreign_keys=ON;")
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
        _current_db_url = url
    return _engine

def dispose_engine():
    """Close all connections and release file handles (Windows)."""
    global _engine, _SessionLocal, _current_db_url
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
    _current_db_url = None

def get_sessionmaker() -> sessionmaker:
    if _SessionLocal is None:
        raise RuntimeError("DB not initialized. Call init_sqlite() first.")
    return _SessionLocal

def get_engine():
    if _engine is None:
        raise RuntimeError("DB not initialized. Call init_sqlite() first.")
    return _engine

def create_all_for_dev():
    eng = get_engine()
    Base.metadata.create_all(eng)
