from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251129_0006"
down_revision = "20251018_0005"
branch_labels = None
depends_on = None


def _has_table(insp, table_name: str) -> bool:
    try:
        return table_name in insp.get_table_names()
    except Exception:
        return False


def _has_column(insp, table_name: str, column_name: str) -> bool:
    try:
        return any(col["name"] == column_name for col in insp.get_columns(table_name))
    except Exception:
        return False


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if not _has_table(insp, "candidate_pool"):
        op.create_table(
            "candidate_pool",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("symbol", sa.String(32), nullable=False, unique=True),
            sa.Column("added_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("added_date", sa.Date, nullable=True),
            sa.Column("added_run_id", sa.String(20), nullable=True),
            sa.Column("added_as_of", sa.String(16), nullable=True),
            sa.Column("last_seen_at", sa.DateTime, nullable=True),
            sa.Column("last_seen_run_id", sa.String(20), nullable=True),
            sa.Column("last_seen_as_of", sa.String(16), nullable=True),
            sa.Column("last_price", sa.Float, nullable=True),
            sa.Column("last_score", sa.Float, nullable=True),
            sa.Column("last_adx14", sa.Float, nullable=True),
            sa.Column("last_atr_pct", sa.Float, nullable=True),
            sa.Column("last_r_multiple", sa.Float, nullable=True),
            sa.Column("last_prox_52w_high_pct", sa.Float, nullable=True),
            sa.Column("last_liquidity", sa.Float, nullable=True),
            sa.Column("last_ema20", sa.Float, nullable=True),
            sa.Column("rank_score", sa.Float, nullable=True),
            sa.Column("rank_ord", sa.Integer, nullable=True),
            sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
            sa.Column("exit_reason", sa.String(64), nullable=True),
            sa.Column("removed_at", sa.DateTime, nullable=True),
            sa.Column("removed_run_id", sa.String(20), nullable=True),
            sa.Column("reasons_json", sa.JSON, nullable=True),
        )
        op.create_index("ix_candidate_pool_symbol", "candidate_pool", ["symbol"])
        op.create_index("ix_candidate_pool_status", "candidate_pool", ["status"])
        op.create_index("ix_candidate_pool_status_rank", "candidate_pool", ["status", "rank_ord"])
    else:
        # Ensure new columns exist when upgrading older DBs.
        with op.batch_alter_table("candidate_pool", recreate="auto") as batch:
            for name, col in [
                ("added_date", sa.Column("added_date", sa.Date, nullable=True)),
                ("added_run_id", sa.Column("added_run_id", sa.String(20), nullable=True)),
                ("added_as_of", sa.Column("added_as_of", sa.String(16), nullable=True)),
                ("last_seen_at", sa.Column("last_seen_at", sa.DateTime, nullable=True)),
                ("last_seen_run_id", sa.Column("last_seen_run_id", sa.String(20), nullable=True)),
                ("last_seen_as_of", sa.Column("last_seen_as_of", sa.String(16), nullable=True)),
                ("last_price", sa.Column("last_price", sa.Float, nullable=True)),
                ("last_score", sa.Column("last_score", sa.Float, nullable=True)),
                ("last_adx14", sa.Column("last_adx14", sa.Float, nullable=True)),
                ("last_atr_pct", sa.Column("last_atr_pct", sa.Float, nullable=True)),
                ("last_r_multiple", sa.Column("last_r_multiple", sa.Float, nullable=True)),
                ("last_prox_52w_high_pct", sa.Column("last_prox_52w_high_pct", sa.Float, nullable=True)),
                ("last_liquidity", sa.Column("last_liquidity", sa.Float, nullable=True)),
                ("last_ema20", sa.Column("last_ema20", sa.Float, nullable=True)),
                ("rank_score", sa.Column("rank_score", sa.Float, nullable=True)),
                ("rank_ord", sa.Column("rank_ord", sa.Integer, nullable=True)),
                ("status", sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE")),
                ("exit_reason", sa.Column("exit_reason", sa.String(64), nullable=True)),
                ("removed_at", sa.Column("removed_at", sa.DateTime, nullable=True)),
                ("removed_run_id", sa.Column("removed_run_id", sa.String(20), nullable=True)),
                ("reasons_json", sa.Column("reasons_json", sa.JSON, nullable=True)),
            ]:
                if not _has_column(insp, "candidate_pool", name):
                    batch.add_column(col)
        insp = sa.inspect(bind)
        if "ix_candidate_pool_symbol" not in [ix["name"] for ix in insp.get_indexes("candidate_pool")]:
            op.create_index("ix_candidate_pool_symbol", "candidate_pool", ["symbol"])
        if "ix_candidate_pool_status" not in [ix["name"] for ix in insp.get_indexes("candidate_pool")]:
            op.create_index("ix_candidate_pool_status", "candidate_pool", ["status"])
        if "ix_candidate_pool_status_rank" not in [ix["name"] for ix in insp.get_indexes("candidate_pool")]:
            op.create_index("ix_candidate_pool_status_rank", "candidate_pool", ["status", "rank_ord"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if _has_table(insp, "candidate_pool"):
        for ix in ("ix_candidate_pool_status_rank", "ix_candidate_pool_status", "ix_candidate_pool_symbol"):
            if ix in [i["name"] for i in insp.get_indexes("candidate_pool")]:
                op.drop_index(ix, table_name="candidate_pool")
        op.drop_table("candidate_pool")
