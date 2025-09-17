# backend/app/core/db.py 
from __future__ import annotations

from pathlib import Path
from typing import Optional, Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool

from alembic.config import Config as AlembicConfig
from alembic import command as alembic_command
import os

from .config import get_settings
from ..repos.models import Base  # ensures models are importable before migrations

# ADDED: minimal logging + threading for timeout
import logging, os, threading, time
_log = logging.getLogger("app.core.db")

_engine = None
_SessionLocal: Optional[sessionmaker] = None
_current_db_url: Optional[str] = None


def _alembic_upgrade_head(sqlite_path: str) -> None:
    """
    Run Alembic migrations programmatically against the provided SQLite file.
    Tests can point this at a temp DB path; production uses settings.storage.sqlite_path.
    """
    # ---- Non-blocking lock to prevent double-run under uvicorn --reload ----
    lock_path = Path(sqlite_path).with_suffix(".alembic.lock")
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
    except FileExistsError:
        _log.info("alembic.upgrade: lock present (%s) — skipping (another process will run it)", lock_path)
        return
    # -----------------------------------------------------------------------

    try:
        backend_dir = Path(__file__).resolve().parents[2]
        cfg = AlembicConfig(str(backend_dir / "alembic.ini"))
        # Use posix path + short timeout to avoid indefinite lock waits on Windows
        db_url = f"sqlite:///{Path(sqlite_path).resolve().as_posix()}?timeout=2.0"
        cfg.set_main_option("sqlalchemy.url", db_url)
        _log.info("alembic.upgrade: %s", db_url)
        alembic_command.upgrade(cfg, "head")
    finally:
        try:
            if lock_path.exists():
                lock_path.unlink()
        except Exception:
            _log.warning("alembic.upgrade: failed to remove lock %s", lock_path)


# ADDED: tiny wrapper to avoid dev hangs — try upgrade, but don't block forever
def _try_alembic_upgrade_with_timeout(sqlite_path: str, seconds: float = 3.0) -> None:
    """
    Attempt Alembic upgrade, but don't let it hang dev server forever.
    If not finished within `seconds`, skip (log a warning) and continue boot.
    """
    done = {"ok": False}
    def _run():
        try:
            _alembic_upgrade_head(sqlite_path)
            done["ok"] = True
        except Exception:
            _log.exception("alembic.upgrade: failed")

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=seconds)
    if t.is_alive():
        _log.warning("alembic.upgrade: taking too long (>%.1fs) — skipping for dev boot", seconds)
        # We let the thread die when process restarts; do not block startup.


def init_sqlite(db_path: str | None = None):
    """
    Initialize engine + sessionmaker for a SQLite DB file.
    - Runs Alembic to head before creating the engine.
    - Uses NullPool to release file handles promptly (Windows-friendly).
    - Enables WAL + foreign_keys pragmas.
    """
    cfg = get_settings()
    path = db_path or cfg.storage.sqlite_path
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    # CHANGED: use non-blocking attempt with timeout (prevents reload hangs on Windows)
    #_try_alembic_upgrade_with_timeout(path, seconds=3.0)
    if os.getenv("APP_DISABLE_ALEMBIC", "").lower() in ("1", "true", "yes"):
        _log.info("alembic: disabled via APP_DISABLE_ALEMBIC")
    else:
        _alembic_upgrade_head(path)    

    global _engine, _SessionLocal, _current_db_url
    url = f"sqlite:///{path}"
    if _engine is None or _current_db_url != url:
        _log.info("db.init_sqlite: creating engine url=%s", url)
        _engine = create_engine(
            url,
            connect_args={"check_same_thread": False, "timeout": 2.0},  # short timeout avoids hangs
            poolclass=NullPool,          # important on Windows to avoid file locks
            pool_pre_ping=True,
            future=True,
        )
        # Pragmas
        with _engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
            conn.exec_driver_sql("PRAGMA foreign_keys=ON;")
            conn.exec_driver_sql("SELECT 1")
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
        _current_db_url = url
        _log.info("db.init_sqlite: engine ready path=%s", Path(path))
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


# -------- FastAPI dependency (NEW) --------
def get_session() -> Iterator[Session]:
    """
    FastAPI dependency that yields a SQLAlchemy Session and always closes it.
    Usage: Depends(get_session)
    """
    sm = get_sessionmaker()
    db: Session = sm()
    try:
        yield db
    finally:
        db.close()

