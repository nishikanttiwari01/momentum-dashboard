"""add alerts tables

Revision ID: 20250921_01
Revises:
Create Date: 2025-09-21 12:00:00

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20250921_01"
down_revision = None  # set to last revision id if you have one
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "alert_state",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("rule_code", sa.String(64), nullable=False),
        sa.Column("last_score", sa.Integer, nullable=True),
        sa.Column("last_fired_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_fired_local_date", sa.Date(), nullable=True),
        sa.Column("last_fired_run_id", sa.String(32), nullable=True),
        sa.UniqueConstraint("symbol", "rule_code", name="uq_alertstate_symbol_rule"),
    )
    op.create_index("ix_alertstate_symbol_rule", "alert_state", ["symbol", "rule_code"])
    op.create_index("ix_alert_state_symbol", "alert_state", ["symbol"])

    op.create_table(
        "alert_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("run_id", sa.String(32), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("rule_code", sa.String(64), nullable=False),
        sa.Column("score", sa.Integer, nullable=True),
        sa.Column("channels_sent_json", sa.JSON, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
    )
    op.create_index("ix_alertevents_symbol_rule", "alert_events", ["symbol", "rule_code"])
    op.create_index("ix_alertevents_run", "alert_events", ["run_id"])


def downgrade():
    op.drop_index("ix_alertevents_run", table_name="alert_events")
    op.drop_index("ix_alertevents_symbol_rule", table_name="alert_events")
    op.drop_table("alert_events")
    op.drop_index("ix_alert_state_symbol", table_name="alert_state")
    op.drop_index("ix_alertstate_symbol_rule", table_name="alert_state")
    op.drop_table("alert_state")
