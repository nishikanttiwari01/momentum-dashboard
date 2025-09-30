from __future__ import annotations
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20250930_0003"
down_revision = "d65fc156cce6"  # or your latest head; adjust if needed
branch_labels = None
depends_on = None

def upgrade() -> None:
    # SQLite-safe: use batch_alter_table for nullable changes
    with op.batch_alter_table("positions") as batch:
        batch.alter_column(
            "entry_price_locked",
            existing_type=sa.Float(),
            nullable=True,  # allow NULL to represent "unlocked"
        )
        batch.add_column(
            sa.Column(
                "trade_on",
                sa.Boolean(),
                server_default=sa.text("0"),
                nullable=False,
            )
        )
    op.create_index("ix_positions_trade_on", "positions", ["trade_on"], unique=False)

def downgrade() -> None:
    op.drop_index("ix_positions_trade_on", table_name="positions")
    with op.batch_alter_table("positions") as batch:
        batch.drop_column("trade_on")
        batch.alter_column(
            "entry_price_locked",
            existing_type=sa.Float(),
            nullable=False,
        )
