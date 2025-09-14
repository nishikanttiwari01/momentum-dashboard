from __future__ import annotations
from logging.config import fileConfig
import os, sys

# --- add the backend folder to sys.path so 'app' is importable ---
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from alembic import context
from app.repos.models import Base  # now resolvable

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def _resolve_db_url() -> str:
    # Priority: env(DB_URL) → alembic.ini sqlalchemy.url → default local path
    return (
        os.environ.get("DB_URL")
        or config.get_main_option("sqlalchemy.url")
        or "sqlite:///./data/local.db"
    )

def run_migrations_offline():
    url = _resolve_db_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_name="sqlite",
        compare_type=True,
        compare_server_default=True,
        render_as_batch=True,  # safer ALTERs on SQLite
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    url = _resolve_db_url()
    connectable = create_engine(url, future=True, poolclass=NullPool)
    try:
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
                compare_server_default=True,
                render_as_batch=True,  # safer ALTERs on SQLite
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        # Ensure file handles are released (important on Windows)
        connectable.dispose()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
