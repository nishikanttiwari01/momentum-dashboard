from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251012_0004"
down_revision = "20250930_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("positions") as batch:
        batch.add_column(sa.Column("sell_price", sa.Float(), nullable=True))
        batch.add_column(sa.Column("sold_at", sa.DateTime(), nullable=True))

    # symbol index was unique; re-create as non-unique to allow history rows
    op.drop_index(op.f("ix_positions_symbol"), table_name="positions")
    op.create_index("ix_positions_symbol", "positions", ["symbol"], unique=False)

    # Useful filters for history + active lookups
    op.create_index("ix_positions_sold_at", "positions", ["sold_at"], unique=False)
    op.create_index("ix_positions_symbol_trade_on", "positions", ["symbol", "trade_on"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_positions_symbol_trade_on", table_name="positions")
    op.drop_index("ix_positions_sold_at", table_name="positions")
    op.drop_index("ix_positions_symbol", table_name="positions")
    op.create_index(op.f("ix_positions_symbol"), "positions", ["symbol"], unique=True)

    with op.batch_alter_table("positions") as batch:
        batch.drop_column("sold_at")
        batch.drop_column("sell_price")
