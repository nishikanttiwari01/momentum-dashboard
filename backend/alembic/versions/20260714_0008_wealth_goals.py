from __future__ import annotations

from datetime import date

from alembic import op
import sqlalchemy as sa

revision = "20260714_0008"
down_revision = "20260714_0007"
branch_labels = None
depends_on = None

GOAL_ID = "00000000-0000-0000-0000-000000000015"


def upgrade() -> None:
    goals = op.create_table(
        "wealth_goals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("target_amount_inr", sa.Float, nullable=False),
        sa.Column("deadline", sa.Date, nullable=False),
        sa.Column("is_primary", sa.Boolean, nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_wealth_goals_is_primary", "wealth_goals", ["is_primary"], unique=True)

    scenarios = op.create_table(
        "wealth_goal_scenarios",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("goal_id", sa.String(36), sa.ForeignKey("wealth_goals.id"), nullable=False),
        sa.Column("scenario_key", sa.String(16), nullable=False),
        sa.Column("annual_return_pct", sa.Float, nullable=False),
        sa.Column("monthly_contribution_inr", sa.Float, nullable=False, server_default=sa.text("0")),
        sa.Column("display_order", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("goal_id", "scenario_key"),
    )
    op.create_index("ix_wealth_goal_scenarios_goal_id", "wealth_goal_scenarios", ["goal_id"])

    op.bulk_insert(
        goals,
        [{
            "id": GOAL_ID,
            "name": "₹15 Cr by 2029",
            "target_amount_inr": 150000000.0,
            "deadline": date(2029, 12, 31),
            "is_primary": True,
        }],
    )
    op.bulk_insert(
        scenarios,
        [
            {"id": "00000000-0000-0000-0000-000000000071", "goal_id": GOAL_ID, "scenario_key": "conservative", "annual_return_pct": 7.0, "monthly_contribution_inr": 0.0, "display_order": 0},
            {"id": "00000000-0000-0000-0000-000000000100", "goal_id": GOAL_ID, "scenario_key": "expected", "annual_return_pct": 10.0, "monthly_contribution_inr": 0.0, "display_order": 1},
            {"id": "00000000-0000-0000-0000-000000000130", "goal_id": GOAL_ID, "scenario_key": "optimistic", "annual_return_pct": 13.0, "monthly_contribution_inr": 0.0, "display_order": 2},
        ],
    )


def downgrade() -> None:
    op.drop_table("wealth_goal_scenarios")
    op.drop_table("wealth_goals")
