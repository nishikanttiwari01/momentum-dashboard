from pathlib import Path
import tempfile

from app.core.db import init_sqlite, dispose_engine, get_engine

def test_alembic_upgrade_head_runs_clean():
    # Use a unique temp DB to avoid Windows file-handle conflicts
    tmpdir = tempfile.mkdtemp()
    db_path = Path(tmpdir) / "test_migrations.db"

    # Run migrations and ensure DB is operational
    init_sqlite(str(db_path))

    eng = get_engine()
    with eng.connect() as conn:
        assert conn.exec_driver_sql("SELECT 1").scalar() == 1

    # Dispose so Windows can unlink if needed later
    dispose_engine()

    # DB file should exist after migration
    assert db_path.exists()
    assert db_path.stat().st_size > 0


def test_wealth_foundation_tables_exist():
    tmpdir = tempfile.mkdtemp()
    db_path = Path(tmpdir) / "test_wealth_migrations.db"
    init_sqlite(str(db_path))

    eng = get_engine()
    with eng.connect() as conn:
        names = {
            row[0]
            for row in conn.exec_driver_sql(
                "select name from sqlite_master where type='table'"
            )
        }

    dispose_engine()
    assert {
        "portfolio_imports",
        "portfolio_snapshots",
        "portfolio_assets",
        "portfolio_transactions",
        "portfolio_valuations",
        "portfolio_fx_rates",
    } <= names
