from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260716_0010"
down_revision = "20260715_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("family_wealth_plans") as batch_op:
        batch_op.add_column(
            sa.Column("birth_year", sa.Integer, nullable=False, server_default=sa.text("1984"))
        )
        batch_op.add_column(
            sa.Column("birth_month", sa.Integer, nullable=False, server_default=sa.text("7"))
        )
        batch_op.add_column(
            sa.Column("projection_end_age", sa.Integer, nullable=False, server_default=sa.text("80"))
        )

    with op.batch_alter_table("wealth_goal_scenarios") as batch_op:
        batch_op.add_column(
            sa.Column("property_growth_pct", sa.Float, nullable=False, server_default=sa.text("6"))
        )
        batch_op.add_column(
            sa.Column("step_up_enabled", sa.Boolean, nullable=False, server_default=sa.text("0"))
        )
        batch_op.add_column(
            sa.Column("step_up_pct", sa.Float, nullable=False, server_default=sa.text("6"))
        )
        batch_op.add_column(
            sa.Column("contribution_stop_age", sa.Integer, nullable=False, server_default=sa.text("60"))
        )
        batch_op.alter_column(
            "monthly_contribution_inr",
            existing_type=sa.Float(),
            existing_nullable=False,
            server_default=sa.text("600000"),
        )

    scenarios = sa.table(
        "wealth_goal_scenarios",
        sa.column("scenario_key", sa.String()),
        sa.column("property_growth_pct", sa.Float()),
        sa.column("monthly_contribution_inr", sa.Float()),
    )
    op.execute(scenarios.update().values(monthly_contribution_inr=600000.0))
    op.execute(
        scenarios.update()
        .where(scenarios.c.scenario_key == "conservative")
        .values(property_growth_pct=4.0)
    )
    op.execute(
        scenarios.update()
        .where(scenarios.c.scenario_key == "optimistic")
        .values(property_growth_pct=8.0)
    )


def downgrade() -> None:
    with op.batch_alter_table("wealth_goal_scenarios") as batch_op:
        batch_op.alter_column(
            "monthly_contribution_inr",
            existing_type=sa.Float(),
            existing_nullable=False,
            server_default=sa.text("0"),
        )
        batch_op.drop_column("contribution_stop_age")
        batch_op.drop_column("step_up_pct")
        batch_op.drop_column("step_up_enabled")
        batch_op.drop_column("property_growth_pct")

    with op.batch_alter_table("family_wealth_plans") as batch_op:
        batch_op.drop_column("projection_end_age")
        batch_op.drop_column("birth_month")
        batch_op.drop_column("birth_year")
