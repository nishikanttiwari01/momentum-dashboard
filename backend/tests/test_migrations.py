from pathlib import Path
import sqlite3
import tempfile

import pytest
from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from sqlalchemy.exc import IntegrityError

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


def test_wealth_goal_defaults_are_seeded():
    tmpdir = tempfile.mkdtemp()
    db_path = Path(tmpdir) / "test_wealth_goals.db"
    init_sqlite(str(db_path))

    eng = get_engine()
    with eng.connect() as conn:
        names = {
            row[0]
            for row in conn.exec_driver_sql(
                "select name from sqlite_master where type='table'"
            )
        }
        goal = conn.exec_driver_sql(
            "select id, name, target_amount_inr, deadline, is_primary "
            "from wealth_goals where id = ?",
            ("00000000-0000-0000-0000-000000000015",),
        ).one()
        scenarios = conn.exec_driver_sql(
            "select id, goal_id, scenario_key, annual_return_pct, "
            "monthly_contribution_inr, display_order "
            "from wealth_goal_scenarios order by display_order"
        ).all()

    dispose_engine()
    assert {"wealth_goals", "wealth_goal_scenarios"} <= names
    assert goal == (
        "00000000-0000-0000-0000-000000000015",
        "₹15 Cr by 2029",
        150000000.0,
        "2029-12-31",
        1,
    )
    assert scenarios == [
        (
            "00000000-0000-0000-0000-000000000071",
            "00000000-0000-0000-0000-000000000015",
            "conservative",
            7.0,
            0.0,
            0,
        ),
        (
            "00000000-0000-0000-0000-000000000100",
            "00000000-0000-0000-0000-000000000015",
            "expected",
            10.0,
            0.0,
            1,
        ),
        (
            "00000000-0000-0000-0000-000000000130",
            "00000000-0000-0000-0000-000000000015",
            "optimistic",
            13.0,
            0.0,
            2,
        ),
    ]


def test_multiple_non_primary_wealth_goals_can_coexist():
    tmpdir = tempfile.mkdtemp()
    db_path = Path(tmpdir) / "test_secondary_wealth_goals.db"
    init_sqlite(str(db_path))

    eng = get_engine()
    with eng.begin() as conn:
        for suffix in ("016", "017"):
            conn.exec_driver_sql(
                "insert into wealth_goals "
                "(id, name, target_amount_inr, deadline, is_primary) "
                "values (?, ?, ?, ?, ?)",
                (
                    f"00000000-0000-0000-0000-000000000{suffix}",
                    f"Secondary goal {suffix}",
                    1000000.0,
                    "2030-12-31",
                    0,
                ),
            )

    with eng.connect() as conn:
        secondary_count = conn.exec_driver_sql(
            "select count(*) from wealth_goals where is_primary = 0"
        ).scalar_one()

    dispose_engine()
    assert secondary_count == 2


def test_second_primary_wealth_goal_is_rejected():
    tmpdir = tempfile.mkdtemp()
    db_path = Path(tmpdir) / "test_primary_wealth_goal.db"
    init_sqlite(str(db_path))

    eng = get_engine()
    with pytest.raises(IntegrityError):
        with eng.begin() as conn:
            conn.exec_driver_sql(
                "insert into wealth_goals "
                "(id, name, target_amount_inr, deadline, is_primary) "
                "values (?, ?, ?, ?, ?)",
                (
                    "00000000-0000-0000-0000-000000000016",
                    "Another primary goal",
                    2000000.0,
                    "2030-12-31",
                    1,
                ),
            )

    dispose_engine()


def test_wealth_goal_migration_downgrade_upgrade_round_trip():
    tmpdir = tempfile.mkdtemp()
    db_path = Path(tmpdir) / "test_wealth_goal_round_trip.db"
    init_sqlite(str(db_path))
    dispose_engine()

    backend_dir = Path(__file__).resolve().parents[1]
    cfg = AlembicConfig(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")

    alembic_command.downgrade(cfg, "20260714_0007")
    with sqlite3.connect(db_path) as conn:
        names = {
            row[0]
            for row in conn.execute(
                "select name from sqlite_master where type='table'"
            )
        }
    assert "wealth_goals" not in names
    assert "wealth_goal_scenarios" not in names

    alembic_command.upgrade(cfg, "head")
    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            "select count(*) from wealth_goals where is_primary = 1"
        ).fetchone() == (1,)
        assert conn.execute(
            "select count(*) from wealth_goal_scenarios"
        ).fetchone() == (3,)
