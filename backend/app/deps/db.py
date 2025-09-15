# app/deps/db.py (new)
from contextlib import asynccontextmanager
from app.core import db as core_db

@asynccontextmanager
async def get_session_safe():
    """
    Ensures SQLite is initialized before yielding a session.
    Safe and idempotent for tests and dev.
    """
    if not getattr(core_db, "is_initialized", lambda: False)():
        core_db.init_sqlite()
    with core_db.get_session() as s:
        yield s
