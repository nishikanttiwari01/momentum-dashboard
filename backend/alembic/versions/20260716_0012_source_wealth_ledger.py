from alembic import op
import sqlalchemy as sa


revision = "20260716_0012"
down_revision = "20260716_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wealth_assets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_key", sa.String(64), nullable=False),
        sa.Column("owner", sa.String(120)),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(120)),
        sa.Column("asset_class", sa.String(32), nullable=False),
        sa.Column("market", sa.String(16), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("source_ref", sa.JSON, nullable=False),
        sa.UniqueConstraint("source_key"),
    )
    op.create_index("ix_wealth_assets_source_key", "wealth_assets", ["source_key"], unique=True)
    op.create_index("ix_wealth_assets_asset_class", "wealth_assets", ["asset_class"])
    op.create_table(
        "wealth_asset_observations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("import_id", sa.String(36), sa.ForeignKey("portfolio_imports.id"), nullable=False),
        sa.Column("asset_id", sa.String(36), sa.ForeignKey("wealth_assets.id"), nullable=False),
        sa.Column("source_key", sa.String(64), nullable=False, unique=True),
        sa.Column("observed_on", sa.Date, nullable=False),
        sa.Column("principal", sa.Float),
        sa.Column("market_value", sa.Float),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("source_ref", sa.JSON, nullable=False),
    )
    op.create_index("ix_wealth_asset_observations_import_id", "wealth_asset_observations", ["import_id"])
    op.create_index("ix_wealth_asset_observations_asset_id", "wealth_asset_observations", ["asset_id"])
    op.create_index("ix_wealth_asset_observations_observed_on", "wealth_asset_observations", ["observed_on"])
    op.create_table(
        "wealth_cash_flows",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("import_id", sa.String(36), sa.ForeignKey("portfolio_imports.id"), nullable=False),
        sa.Column("asset_id", sa.String(36), sa.ForeignKey("wealth_assets.id")),
        sa.Column("source_key", sa.String(64), nullable=False, unique=True),
        sa.Column("occurred_on", sa.Date, nullable=False),
        sa.Column("flow_type", sa.String(32), nullable=False),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("source_ref", sa.JSON, nullable=False),
    )
    op.create_index("ix_wealth_cash_flows_import_id", "wealth_cash_flows", ["import_id"])
    op.create_index("ix_wealth_cash_flows_asset_id", "wealth_cash_flows", ["asset_id"])
    op.create_index("ix_wealth_cash_flows_occurred_on", "wealth_cash_flows", ["occurred_on"])
    op.create_index("ix_wealth_cash_flows_flow_type", "wealth_cash_flows", ["flow_type"])
    op.create_table(
        "wealth_reporting_periods",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("import_id", sa.String(36), sa.ForeignKey("portfolio_imports.id"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("label", sa.String(32), nullable=False),
        sa.Column("controls", sa.JSON, nullable=False),
        sa.UniqueConstraint("import_id", "year"),
    )
    op.create_index("ix_wealth_reporting_periods_import_id", "wealth_reporting_periods", ["import_id"])
    op.create_index("ix_wealth_reporting_periods_year", "wealth_reporting_periods", ["year"])
    op.create_table(
        "wealth_reporting_period_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("period_id", sa.String(36), sa.ForeignKey("wealth_reporting_periods.id"), nullable=False),
        sa.Column("metric", sa.String(40), nullable=False),
        sa.Column("source_sheet", sa.String(64), nullable=False),
        sa.Column("source_cell", sa.String(16), nullable=False),
        sa.Column("observed_on", sa.Date),
        sa.UniqueConstraint("period_id", "metric"),
    )
    op.create_index("ix_wealth_reporting_period_sources_period_id", "wealth_reporting_period_sources", ["period_id"])
    op.create_index("ix_wealth_reporting_period_sources_metric", "wealth_reporting_period_sources", ["metric"])
    op.create_index("ix_wealth_reporting_period_sources_observed_on", "wealth_reporting_period_sources", ["observed_on"])


def downgrade() -> None:
    op.drop_table("wealth_reporting_period_sources")
    op.drop_table("wealth_reporting_periods")
    op.drop_table("wealth_cash_flows")
    op.drop_table("wealth_asset_observations")
    op.drop_table("wealth_assets")
