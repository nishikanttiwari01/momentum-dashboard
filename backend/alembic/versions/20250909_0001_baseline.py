from __future__ import annotations
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20250909_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("rule_type", sa.String(length=32), nullable=False),
        sa.Column("rule_value", sa.String(length=64), nullable=True),
        sa.Column("channels", sa.JSON(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alerts")),
    )
    op.create_index(op.f("ix_alerts_symbol"), "alerts", ["symbol"], unique=False)
    op.create_index(op.f("ix_alerts_enabled"), "alerts", ["enabled"], unique=False)
    op.create_index("ix_alerts_symbol_enabled", "alerts", ["symbol", "enabled"], unique=False)
    op.create_index(op.f("ix_alerts_created_at"), "alerts", ["created_at"], unique=False)
    op.create_index(op.f("ix_alerts_updated_at"), "alerts", ["updated_at"], unique=False)

    op.create_table(
        "watchlist",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_watchlist")),
    )
    op.create_index(op.f("ix_watchlist_symbol"), "watchlist", ["symbol"], unique=True)

    op.create_table(
        "history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("as_of", sa.DateTime(), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("pnl_pct", sa.Float(), nullable=True),
        sa.Column("run_id", sa.String(length=20), nullable=True),
        sa.Column("meta_json", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_history")),
        sa.UniqueConstraint("symbol", "as_of", name="uq_history_symbol_asof"),
    )
    op.create_index(op.f("ix_history_symbol"), "history", ["symbol"], unique=False)
    op.create_index(op.f("ix_history_as_of"), "history", ["as_of"], unique=False)
    op.create_index(op.f("ix_history_asof_symbol"), "history", ["as_of", "symbol"], unique=False)
    op.create_index(op.f("ix_history_run_id"), "history", ["run_id"], unique=False)

    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
    )
    op.create_index(op.f("ix_jobs_name"), "jobs", ["name"], unique=False)
    op.create_index(op.f("ix_jobs_run_id"), "jobs", ["run_id"], unique=False)
    op.create_index(op.f("ix_jobs_status"), "jobs", ["status"], unique=False)

    op.create_table(
        "settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value_yaml", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_settings")),
    )
    op.create_index(op.f("ix_settings_key"), "settings", ["key"], unique=True)

    op.create_table(
        "positions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("entry_price_locked", sa.Float(), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=True),
        sa.Column("stop_now", sa.Float(), nullable=True),
        sa.Column("exit_close_threshold", sa.Float(), nullable=True),
        sa.Column("breakeven_active", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("euphoria_on", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_positions")),
    )
    op.create_index(op.f("ix_positions_symbol"), "positions", ["symbol"], unique=True)
    op.create_index(op.f("ix_positions_breakeven_active"), "positions", ["breakeven_active"], unique=False)
    op.create_index(op.f("ix_positions_euphoria_on"), "positions", ["euphoria_on"], unique=False)

    op.create_table(
        "snapshot_pins",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("run_id", sa.String(length=20), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_snapshot_pins")),
    )
    op.create_index(op.f("ix_snapshot_pins_symbol"), "snapshot_pins", ["symbol"], unique=True)
    op.create_index(op.f("ix_snapshot_pins_run_id"), "snapshot_pins", ["run_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_snapshot_pins_run_id"), table_name="snapshot_pins")
    op.drop_index(op.f("ix_snapshot_pins_symbol"), table_name="snapshot_pins")
    op.drop_table("snapshot_pins")

    op.drop_index(op.f("ix_positions_euphoria_on"), table_name="positions")
    op.drop_index(op.f("ix_positions_breakeven_active"), table_name="positions")
    op.drop_index(op.f("ix_positions_symbol"), table_name="positions")
    op.drop_table("positions")

    op.drop_index(op.f("ix_settings_key"), table_name="settings")
    op.drop_table("settings")

    op.drop_index(op.f("ix_jobs_status"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_run_id"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_name"), table_name="jobs")
    op.drop_table("jobs")

    op.drop_index(op.f("ix_history_run_id"), table_name="history")
    op.drop_index(op.f("ix_history_asof_symbol"), table_name="history")
    op.drop_index(op.f("ix_history_as_of"), table_name="history")
    op.drop_index(op.f("ix_history_symbol"), table_name="history")
    op.drop_table("history")

    op.drop_index(op.f("ix_watchlist_symbol"), table_name="watchlist")
    op.drop_table("watchlist")

    op.drop_index(op.f("ix_alerts_updated_at"), table_name="alerts")
    op.drop_index(op.f("ix_alerts_created_at"), table_name="alerts")
    op.drop_index("ix_alerts_symbol_enabled", table_name="alerts")
    op.drop_index(op.f("ix_alerts_enabled"), table_name="alerts")
    op.drop_index(op.f("ix_alerts_symbol"), table_name="alerts")
    op.drop_table("alerts")
