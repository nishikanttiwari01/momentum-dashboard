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
            600000.0,
            0,
        ),
        (
            "00000000-0000-0000-0000-000000000100",
            "00000000-0000-0000-0000-000000000015",
            "expected",
            10.0,
            600000.0,
            1,
        ),
        (
            "00000000-0000-0000-0000-000000000130",
            "00000000-0000-0000-0000-000000000015",
            "optimistic",
            13.0,
            600000.0,
            2,
        ),
    ]


def test_family_wealth_plan_defaults_are_seeded():
    tmpdir = tempfile.mkdtemp()
    db_path = Path(tmpdir) / "test_family_wealth_plan.db"
    init_sqlite(str(db_path))

    eng = get_engine()
    with eng.connect() as conn:
        names = {
            row[0]
            for row in conn.exec_driver_sql(
                "select name from sqlite_master where type='table'"
            )
        }
        plan = conn.exec_driver_sql(
            "select id, base_age, monthly_contribution_inr, contribution_step_up_enabled, "
            "contribution_step_up_pct, monthly_rent_inr, rent_growth_pct, "
            "reinvest_rent_until, property_growth_pct, withdrawal_rate_pct, "
            "amber_margin_pct "
            "from family_wealth_plans"
        ).one()
        goals = conn.exec_driver_sql(
            "select id, goal_key, goal_type, current_value_amount_inr, target_date, "
            "inflation_pct, funding_treatment, priority, enabled, display_order "
            "from family_wealth_goals order by display_order"
        ).all()

    dispose_engine()
    assert {"family_wealth_plans", "family_wealth_goals"} <= names
    assert plan == (
        "00000000-0000-0000-0000-000000000001",
        42, 600000.0, 0, 6.0, 45000.0, 6.0, "2029-12-31", 6.0, 3.5, 10.0
    )
    assert goals == [
        ("00000000-0000-0000-0000-000000000101", "child_1_education", "education", 20000000.0, "2032-12-31", 8.0, "expense", 1, 1, 0),
        ("00000000-0000-0000-0000-000000000102", "passive_income", "passive_income", 200000.0, "2029-12-31", 0.0, "income_target", 2, 1, 1),
        ("00000000-0000-0000-0000-000000000103", "bangalore_house", "house", 30000000.0, "2036-12-31", 8.0, "asset_conversion", 3, 1, 2),
        ("00000000-0000-0000-0000-000000000104", "child_2_education", "education", 20000000.0, "2038-12-31", 8.0, "expense", 4, 1, 3),
        ("00000000-0000-0000-0000-000000000105", "child_1_marriage", "marriage", 5000000.0, "2042-12-31", 6.0, "expense", 5, 1, 4),
        ("00000000-0000-0000-0000-000000000106", "child_2_marriage", "marriage", 5000000.0, "2044-12-31", 6.0, "expense", 6, 1, 5),
    ]


def test_family_wealth_goal_defaults_enabled_and_goal_key_is_unique_per_plan():
    tmpdir = tempfile.mkdtemp()
    db_path = Path(tmpdir) / "test_family_wealth_goal_constraints.db"
    init_sqlite(str(db_path))

    eng = get_engine()
    insert_sql = (
        "insert into family_wealth_goals "
        "(id, plan_id, goal_key, name, goal_type, current_value_amount_inr, "
        "target_date, inflation_pct, funding_treatment, priority, display_order) "
        "values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )
    values = (
        "00000000-0000-0000-0000-000000000107",
        "00000000-0000-0000-0000-000000000001",
        "future_goal",
        "Future goal",
        "education",
        1000000.0,
        "2045-12-31",
        8.0,
        "expense",
        7,
        6,
    )
    with eng.begin() as conn:
        conn.exec_driver_sql(insert_sql, values)
        assert conn.exec_driver_sql(
            "select enabled from family_wealth_goals where id = ?", (values[0],)
        ).scalar_one() == 1

    with pytest.raises(IntegrityError):
        with eng.begin() as conn:
            conn.exec_driver_sql(
                insert_sql,
                ("00000000-0000-0000-0000-000000000108",) + values[1:],
            )

    dispose_engine()


def test_lifetime_runway_assumptions_upgrade_from_0009_and_round_trip():
    tmpdir = tempfile.mkdtemp()
    db_path = Path(tmpdir) / "test_lifetime_runway_round_trip.db"
    backend_dir = Path(__file__).resolve().parents[1]
    cfg = AlembicConfig(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")

    alembic_command.upgrade(cfg, "20260715_0009")
    alembic_command.upgrade(cfg, "20260716_0010")

    with sqlite3.connect(db_path) as conn:
        plan = conn.execute(
            "select birth_year, birth_month, projection_end_age "
            "from family_wealth_plans"
        ).fetchone()
        scenarios = {
            row[0]: row[1:]
            for row in conn.execute(
                "select scenario_key, annual_return_pct, property_growth_pct, "
                "monthly_contribution_inr, step_up_enabled, step_up_pct, "
                "contribution_stop_age from wealth_goal_scenarios"
            )
        }

    assert plan == (1984, 7, 80)
    assert scenarios == {
        "conservative": (7.0, 4.0, 600000.0, 0, 6.0, 60),
        "expected": (10.0, 6.0, 600000.0, 0, 6.0, 60),
        "optimistic": (13.0, 8.0, 600000.0, 0, 6.0, 60),
    }

    alembic_command.downgrade(cfg, "20260715_0009")
    with sqlite3.connect(db_path) as conn:
        plan_columns = {row[1] for row in conn.execute("pragma table_info(family_wealth_plans)")}
        scenario_columns = {row[1] for row in conn.execute("pragma table_info(wealth_goal_scenarios)")}
        returns = conn.execute(
            "select scenario_key, annual_return_pct from wealth_goal_scenarios "
            "order by display_order"
        ).fetchall()
    assert {"birth_year", "birth_month", "projection_end_age"}.isdisjoint(plan_columns)
    assert {
        "property_growth_pct", "step_up_enabled", "step_up_pct", "contribution_stop_age"
    }.isdisjoint(scenario_columns)
    assert returns == [("conservative", 7.0), ("expected", 10.0), ("optimistic", 13.0)]

    alembic_command.upgrade(cfg, "20260716_0010")
    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            "select birth_year, birth_month, projection_end_age from family_wealth_plans"
        ).fetchone() == (1984, 7, 80)
        assert conn.execute(
            "select property_growth_pct, monthly_contribution_inr, step_up_enabled, "
            "step_up_pct, contribution_stop_age from wealth_goal_scenarios "
            "where scenario_key = 'expected'"
        ).fetchone() == (6.0, 600000.0, 0, 6.0, 60)


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
    assert "family_wealth_plans" not in names
    assert "family_wealth_goals" not in names

    alembic_command.upgrade(cfg, "head")
    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            "select count(*) from wealth_goals where is_primary = 1"
        ).fetchone() == (1,)
        assert conn.execute(
            "select count(*) from wealth_goal_scenarios"
        ).fetchone() == (3,)
