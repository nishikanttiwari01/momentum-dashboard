from __future__ import annotations

from datetime import date

from alembic import op
import sqlalchemy as sa

revision = "20260715_0009"
down_revision = "20260714_0008"
branch_labels = None
depends_on = None

PLAN_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    plans = op.create_table(
        "family_wealth_plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("base_age", sa.Integer, nullable=False),
        sa.Column("monthly_contribution_inr", sa.Float, nullable=False),
        sa.Column("contribution_step_up_enabled", sa.Boolean, nullable=False),
        sa.Column("contribution_step_up_pct", sa.Float, nullable=False),
        sa.Column("monthly_rent_inr", sa.Float, nullable=False),
        sa.Column("rent_growth_pct", sa.Float, nullable=False),
        sa.Column("reinvest_rent_until", sa.Date, nullable=False),
        sa.Column("property_growth_pct", sa.Float, nullable=False),
        sa.Column("withdrawal_rate_pct", sa.Float, nullable=False),
        sa.Column("amber_margin_pct", sa.Float, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    goals = op.create_table(
        "family_wealth_goals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("plan_id", sa.String(36), sa.ForeignKey("family_wealth_plans.id"), nullable=False),
        sa.Column("goal_key", sa.String(64), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("goal_type", sa.String(32), nullable=False),
        sa.Column("current_value_amount_inr", sa.Float, nullable=False),
        sa.Column("target_date", sa.Date, nullable=False),
        sa.Column("inflation_pct", sa.Float, nullable=False),
        sa.Column("funding_treatment", sa.String(32), nullable=False),
        sa.Column("priority", sa.Integer, nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False),
        sa.Column("display_order", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("plan_id", "goal_key"),
    )
    op.create_index("ix_family_wealth_goals_plan_id", "family_wealth_goals", ["plan_id"])

    op.bulk_insert(
        plans,
        [{
            "id": PLAN_ID,
            "base_age": 42,
            "monthly_contribution_inr": 600000.0,
            "contribution_step_up_enabled": False,
            "contribution_step_up_pct": 6.0,
            "monthly_rent_inr": 45000.0,
            "rent_growth_pct": 6.0,
            "reinvest_rent_until": date(2029, 12, 31),
            "property_growth_pct": 6.0,
            "withdrawal_rate_pct": 3.5,
            "amber_margin_pct": 10.0,
        }],
    )
    goal_defaults = [
        ("101", "child_1_education", "Child 1 education", "education", 20000000.0, date(2032, 12, 31), 8.0, "expense"),
        ("102", "passive_income", "Passive income", "passive_income", 200000.0, date(2029, 12, 31), 0.0, "income_target"),
        ("103", "bangalore_house", "Bangalore house", "property", 30000000.0, date(2036, 12, 31), 8.0, "asset_conversion"),
        ("104", "child_2_education", "Child 2 education", "education", 20000000.0, date(2038, 12, 31), 8.0, "expense"),
        ("105", "child_1_marriage", "Child 1 marriage", "marriage", 5000000.0, date(2042, 12, 31), 6.0, "expense"),
        ("106", "child_2_marriage", "Child 2 marriage", "marriage", 5000000.0, date(2044, 12, 31), 6.0, "expense"),
    ]
    op.bulk_insert(
        goals,
        [
            {
                "id": f"00000000-0000-0000-0000-000000000{suffix}",
                "plan_id": PLAN_ID,
                "goal_key": goal_key,
                "name": name,
                "goal_type": goal_type,
                "current_value_amount_inr": amount,
                "target_date": target_date,
                "inflation_pct": inflation_pct,
                "funding_treatment": funding_treatment,
                "priority": display_order + 1,
                "enabled": True,
                "display_order": display_order,
            }
            for display_order, (
                suffix, goal_key, name, goal_type, amount, target_date,
                inflation_pct, funding_treatment,
            ) in enumerate(goal_defaults)
        ],
    )


def downgrade() -> None:
    op.drop_table("family_wealth_goals")
    op.drop_table("family_wealth_plans")
