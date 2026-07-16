from alembic import op
import sqlalchemy as sa

revision = "20260716_0011"
down_revision = "20260716_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolio_annual_review_overrides",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("opening_net_worth_inr", sa.Float),
        sa.Column("contributions_inr", sa.Float),
        sa.Column("investment_gain_inr", sa.Float),
        sa.Column("property_gain_inr", sa.Float),
        sa.Column("rent_received_inr", sa.Float),
        sa.Column("withdrawals_inr", sa.Float),
        sa.Column("closing_net_worth_inr", sa.Float),
        sa.Column("investment_xirr_pct", sa.Float),
        sa.Column("notes", sa.String(2000)),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("year"),
    )
    op.create_index("ix_portfolio_annual_review_overrides_year", "portfolio_annual_review_overrides", ["year"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_portfolio_annual_review_overrides_year", table_name="portfolio_annual_review_overrides")
    op.drop_table("portfolio_annual_review_overrides")
