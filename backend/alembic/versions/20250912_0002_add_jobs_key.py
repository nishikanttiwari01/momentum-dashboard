from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20250912_0002"
down_revision = "20250909_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite-safe: use batch_alter_table for column + index changes
    with op.batch_alter_table("jobs") as b:
        # New nullable idempotency key (body/header provided); keep nullable to allow legacy rows
        b.add_column(sa.Column("key", sa.String(length=64), nullable=True))
        # Enforce idempotency per (name, key). Unique index allows multiple NULLs (SQLite behavior).
        b.create_index("ix_jobs_name_key", ["name", "key"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("jobs") as b:
        b.drop_index("ix_jobs_name_key")
        b.drop_column("key")
