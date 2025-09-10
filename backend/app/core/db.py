from __future__ import annotations
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .config import get_settings
from ..repos.models import Base

_engine = None
_SessionLocal: sessionmaker | None = None


def init_sqlite(db_path: str | None = None):
    """
    Initialize SQLite engine + sessionmaker with WAL and FKs.
    """
    cfg = get_settings()
    path = db_path or cfg.storage.sqlite_path  # e.g. "./data/local.db"
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    global _engine, _SessionLocal
    _engine = create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
        future=True,
    )

    with _engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
        conn.exec_driver_sql("PRAGMA foreign_keys=ON;")

    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)


def get_sessionmaker() -> sessionmaker:
    if _SessionLocal is None:
        raise RuntimeError("DB not initialized. Call init_sqlite() first.")
    return _SessionLocal


def get_engine():
    if _engine is None:
        raise RuntimeError("DB not initialized. Call init_sqlite() first.")
    return _engine


def create_all_for_dev():
    """
    Optional: create tables directly (dev only). In prod, use Alembic.
    """
    eng = get_engine()
    Base.metadata.create_all(eng)
