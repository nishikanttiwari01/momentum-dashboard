from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260714_0007"
down_revision = "20251129_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolio_imports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("imported_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("issue_counts", sa.JSON, nullable=False),
    )
    op.create_index("ix_portfolio_imports_source_sha256", "portfolio_imports", ["source_sha256"], unique=True)
    op.create_index("ix_portfolio_imports_status", "portfolio_imports", ["status"])
    op.create_table(
        "portfolio_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("import_id", sa.String(36), sa.ForeignKey("portfolio_imports.id"), nullable=False, unique=True),
        sa.Column("as_of", sa.Date, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_portfolio_snapshots_import_id", "portfolio_snapshots", ["import_id"], unique=True)
    op.create_index("ix_portfolio_snapshots_as_of", "portfolio_snapshots", ["as_of"])
    op.create_table(
        "portfolio_assets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("snapshot_id", sa.String(36), sa.ForeignKey("portfolio_snapshots.id"), nullable=False),
        sa.Column("source_key", sa.String(64), nullable=False),
        sa.Column("asset_type", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("market", sa.String(16), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("invested_amount", sa.Float),
        sa.Column("market_value", sa.Float),
        sa.Column("source_ref", sa.JSON, nullable=False),
        sa.UniqueConstraint("snapshot_id", "source_key"),
    )
    op.create_index("ix_portfolio_assets_snapshot_id", "portfolio_assets", ["snapshot_id"])
    op.create_index("ix_portfolio_assets_asset_type", "portfolio_assets", ["asset_type"])
    op.create_index("ix_portfolio_assets_market", "portfolio_assets", ["market"])
    op.create_table(
        "portfolio_transactions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("snapshot_id", sa.String(36), sa.ForeignKey("portfolio_snapshots.id"), nullable=False),
        sa.Column("source_key", sa.String(64), nullable=False),
        sa.Column("asset_id", sa.String(36), sa.ForeignKey("portfolio_assets.id"), nullable=False),
        sa.Column("occurred_on", sa.Date, nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("units", sa.Float),
        sa.Column("unit_price", sa.Float),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("source_ref", sa.JSON, nullable=False),
        sa.UniqueConstraint("snapshot_id", "source_key"),
    )
    op.create_index("ix_portfolio_transactions_snapshot_id", "portfolio_transactions", ["snapshot_id"])
    op.create_index("ix_portfolio_transactions_asset_id", "portfolio_transactions", ["asset_id"])
    op.create_index("ix_portfolio_transactions_occurred_on", "portfolio_transactions", ["occurred_on"])
    op.create_table(
        "portfolio_valuations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("snapshot_id", sa.String(36), sa.ForeignKey("portfolio_snapshots.id"), nullable=False),
        sa.Column("source_key", sa.String(64), nullable=False),
        sa.Column("asset_id", sa.String(36), sa.ForeignKey("portfolio_assets.id"), nullable=False),
        sa.Column("valued_on", sa.Date, nullable=False),
        sa.Column("market_value", sa.Float, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("source_ref", sa.JSON, nullable=False),
        sa.UniqueConstraint("snapshot_id", "source_key"),
    )
    op.create_index("ix_portfolio_valuations_snapshot_id", "portfolio_valuations", ["snapshot_id"])
    op.create_index("ix_portfolio_valuations_asset_id", "portfolio_valuations", ["asset_id"])
    op.create_index("ix_portfolio_valuations_valued_on", "portfolio_valuations", ["valued_on"])
    op.create_table(
        "portfolio_fx_rates",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("base_currency", sa.String(3), nullable=False),
        sa.Column("quote_currency", sa.String(3), nullable=False),
        sa.Column("effective_on", sa.Date, nullable=False),
        sa.Column("rate", sa.Float, nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("fetched_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("base_currency", "quote_currency", "effective_on"),
    )


def downgrade() -> None:
    op.drop_table("portfolio_fx_rates")
    op.drop_table("portfolio_valuations")
    op.drop_table("portfolio_transactions")
    op.drop_table("portfolio_assets")
    op.drop_table("portfolio_snapshots")
    op.drop_table("portfolio_imports")
