from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251018_0005"
down_revision = "20251012_0004"
branch_labels = None
depends_on = None


# -------- helpers --------
def _has_table(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def _has_index(inspector, table_name: str, index_name: str) -> bool:
    return any(idx["name"] == index_name for idx in inspector.get_indexes(table_name))


def _drop_leftover_tmp(table_base: str) -> None:
    # SQLite can leave temp tables around if a prior batch failed mid-flight
    op.execute(f"DROP TABLE IF EXISTS _alembic_tmp_{table_base}")


# -------- migration --------
def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # =========================
    # 1) alert_events (create or extend)
    # =========================
    if not _has_table(insp, "alert_events"):
        op.create_table(
            "alert_events",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("symbol", sa.String(32), nullable=False),
            sa.Column("rule_code", sa.String(64), nullable=False),
            sa.Column("severity", sa.String(16), nullable=False),
            sa.Column("digest_bucket", sa.String(16), nullable=False),
            sa.Column("mode", sa.String(16), nullable=False),  # EOD|INTRADAY
            sa.Column("trading_date", sa.Date, nullable=False),
            sa.Column("bucket_ord", sa.Integer, nullable=False, server_default=sa.text("0")),
            sa.Column("intraday_bucket_label", sa.String(16), nullable=True),
            sa.Column("send_type", sa.String(16), nullable=False, server_default="IMMEDIATE"),  # IMMEDIATE|DIGEST
            sa.Column("digest_id", sa.String(64), nullable=True),
            sa.Column("title_rendered", sa.Text, nullable=False),
            sa.Column("body_rendered", sa.Text, nullable=False),
            sa.Column("score_at_fire", sa.Float, nullable=True),
            sa.Column("next_action_code", sa.String(32), nullable=True),
            sa.Column("triggered_by", sa.String(24), nullable=False, server_default="SCHEDULE"),
            sa.Column("profile", sa.String(16), nullable=True),
            sa.Column("config_version", sa.Integer, nullable=True),
            sa.Column("context_json", sa.JSON, nullable=True),
            sa.Column("details_json", sa.JSON, nullable=True),
            sa.Column("channels_summary_json", sa.JSON, nullable=False, server_default=sa.text("'{}'")),
            sa.Column("fired_at_utc", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
    else:
        # Clean up any leftover temp tables from a prior failed run
        _drop_leftover_tmp("alert_events")

        # Pre-drop legacy index that references run_id (avoid recreate on missing column)
        if _has_index(insp, "alert_events", "ix_alertevents_run"):
            op.drop_index("ix_alertevents_run", table_name="alert_events")

        # ---- BATCH #1: renames/drops only ----
        has_created_at = _has_column(insp, "alert_events", "created_at_utc")
        has_fired_at = _has_column(insp, "alert_events", "fired_at_utc")
        has_sent = _has_column(insp, "alert_events", "channels_sent_json")
        has_summary = _has_column(insp, "alert_events", "channels_summary_json")
        has_run_id = _has_column(insp, "alert_events", "run_id")

        with op.batch_alter_table("alert_events", recreate="auto") as batch:
            if has_created_at and not has_fired_at:
                batch.alter_column("created_at_utc", new_column_name="fired_at_utc")
            if has_sent and not has_summary:
                batch.alter_column("channels_sent_json", new_column_name="channels_summary_json")
            if has_run_id:
                batch.drop_column("run_id")

        # Refresh inspector and ensure temp is gone
        insp = sa.inspect(bind)
        _drop_leftover_tmp("alert_events")

        # ---- BATCH #2: add missing columns only ----
        with op.batch_alter_table("alert_events", recreate="auto") as batch:
            need = lambda name: not _has_column(insp, "alert_events", name)

            if need("severity"):
                batch.add_column(sa.Column("severity", sa.String(16), nullable=True))
            if need("digest_bucket"):
                batch.add_column(sa.Column("digest_bucket", sa.String(16), nullable=True))
            if need("mode"):
                batch.add_column(sa.Column("mode", sa.String(16), nullable=True))
            if need("trading_date"):
                batch.add_column(sa.Column("trading_date", sa.Date, nullable=True))
            if need("bucket_ord"):
                batch.add_column(sa.Column("bucket_ord", sa.Integer, nullable=False, server_default=sa.text("0")))
            if need("intraday_bucket_label"):
                batch.add_column(sa.Column("intraday_bucket_label", sa.String(16), nullable=True))
            if need("send_type"):
                batch.add_column(sa.Column("send_type", sa.String(16), nullable=False, server_default="IMMEDIATE"))
            if need("digest_id"):
                batch.add_column(sa.Column("digest_id", sa.String(64), nullable=True))
            if need("title_rendered"):
                batch.add_column(sa.Column("title_rendered", sa.Text, nullable=True))
            if need("body_rendered"):
                batch.add_column(sa.Column("body_rendered", sa.Text, nullable=True))
            if need("score_at_fire"):
                batch.add_column(sa.Column("score_at_fire", sa.Float, nullable=True))
            if need("next_action_code"):
                batch.add_column(sa.Column("next_action_code", sa.String(32), nullable=True))
            if need("triggered_by"):
                batch.add_column(sa.Column("triggered_by", sa.String(24), nullable=False, server_default="SCHEDULE"))
            if need("profile"):
                batch.add_column(sa.Column("profile", sa.String(16), nullable=True))
            if need("config_version"):
                batch.add_column(sa.Column("config_version", sa.Integer, nullable=True))
            if need("context_json"):
                batch.add_column(sa.Column("context_json", sa.JSON, nullable=True))
            if need("details_json"):
                batch.add_column(sa.Column("details_json", sa.JSON, nullable=True))
            if need("channels_summary_json"):
                batch.add_column(sa.Column("channels_summary_json", sa.JSON, nullable=False, server_default=sa.text("'{}'")))
            if need("fired_at_utc"):
                batch.add_column(sa.Column("fired_at_utc", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))

        # Backfill minimal values for legacy rows
        op.execute(sa.text("UPDATE alert_events SET trading_date = DATE(fired_at_utc) WHERE trading_date IS NULL"))
        op.execute(sa.text("UPDATE alert_events SET mode = 'EOD' WHERE mode IS NULL"))
        op.execute(sa.text(
            """
            UPDATE alert_events
               SET title_rendered = COALESCE(title_rendered, rule_code || ' • ' || symbol),
                   body_rendered  = COALESCE(body_rendered, 'Alert generated (legacy import).')
             WHERE title_rendered IS NULL OR body_rendered IS NULL
            """
        ))
        # De-duplicate groups before creating the unique index by assigning bucket_ord = row_number-1
        # Use correlated subquery (SQLite-safe, no window function requirement)
        op.execute(sa.text(
            """
            UPDATE alert_events AS e
               SET bucket_ord = (
                   SELECT COUNT(*) - 1
                     FROM alert_events x
                    WHERE x.rule_code = e.rule_code
                      AND x.symbol = e.symbol
                      AND x.trading_date = e.trading_date
                      AND COALESCE(x.mode,'EOD') = COALESCE(e.mode,'EOD')
                      AND (x.fired_at_utc < e.fired_at_utc OR (x.fired_at_utc = e.fired_at_utc AND x.id <= e.id))
               )
            """
        ))

    # Indexes for alert_events (SQLite-safe, outside batch)
    insp = sa.inspect(bind)
    if not _has_index(insp, "alert_events", "ix_alert_events_fired_at_utc"):
        op.create_index("ix_alert_events_fired_at_utc", "alert_events", ["fired_at_utc"])
    if not _has_index(insp, "alert_events", "ix_alert_events_symbol_trading_date"):
        op.create_index("ix_alert_events_symbol_trading_date", "alert_events", ["symbol", "trading_date"])
    if not _has_index(insp, "alert_events", "ix_alert_events_trading_date_rule"):
        op.create_index("ix_alert_events_trading_date_rule", "alert_events", ["trading_date", "rule_code"])
    if not _has_index(insp, "alert_events", "ix_alert_events_score_at_fire"):
        op.create_index("ix_alert_events_score_at_fire", "alert_events", ["score_at_fire"])
    if not _has_index(insp, "alert_events", "ix_alert_events_next_action_code"):
        op.create_index("ix_alert_events_next_action_code", "alert_events", ["next_action_code"])
    # Use a UNIQUE INDEX instead of a UNIQUE CONSTRAINT (SQLite can't ALTER constraints)
    if not _has_index(insp, "alert_events", "ux_alert_events_code_symbol_date_mode_bucket"):
        op.create_index(
            "ux_alert_events_code_symbol_date_mode_bucket",
            "alert_events",
            ["rule_code", "symbol", "trading_date", "mode", "bucket_ord"],
            unique=True,
        )

    # =========================
    # 2) alert_state (create or extend)
    # =========================
    if not _has_table(insp, "alert_state"):
        op.create_table(
            "alert_state",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("symbol", sa.String(32), nullable=False),
            sa.Column("rule_code", sa.String(64), nullable=False),
            sa.Column("last_fired_at_utc", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_trading_date", sa.Date, nullable=True),
            sa.Column("last_mode", sa.String(16), nullable=True),
            sa.Column("last_bucket_ord", sa.Integer, nullable=True),
            sa.Column("last_score_at_fire", sa.Float, nullable=True),
            sa.Column("last_next_action_code", sa.String(32), nullable=True),
            sa.Column("cooldown_until_utc", sa.DateTime(timezone=True), nullable=True),
        )
        # Ensure uniqueness via UNIQUE INDEX (SQLite-safe)
        op.create_index(
            "ux_alert_state_symbol_rule",
            "alert_state",
            ["symbol", "rule_code"],
            unique=True,
        )
        op.create_index("ix_alert_state_cooldown_until_utc", "alert_state", ["cooldown_until_utc"])
    else:
        _drop_leftover_tmp("alert_state")
        with op.batch_alter_table("alert_state", recreate="auto") as batch:
            if not _has_column(insp, "alert_state", "last_trading_date"):
                batch.add_column(sa.Column("last_trading_date", sa.Date, nullable=True))
            if not _has_column(insp, "alert_state", "last_mode"):
                batch.add_column(sa.Column("last_mode", sa.String(16), nullable=True))
            if not _has_column(insp, "alert_state", "last_bucket_ord"):
                batch.add_column(sa.Column("last_bucket_ord", sa.Integer, nullable=True))
            if not _has_column(insp, "alert_state", "last_score_at_fire"):
                batch.add_column(sa.Column("last_score_at_fire", sa.Float, nullable=True))
            if not _has_column(insp, "alert_state", "last_next_action_code"):
                batch.add_column(sa.Column("last_next_action_code", sa.String(32), nullable=True))
            if not _has_column(insp, "alert_state", "cooldown_until_utc"):
                batch.add_column(sa.Column("cooldown_until_utc", sa.DateTime(timezone=True), nullable=True))

        insp = sa.inspect(bind)
        if not _has_index(insp, "alert_state", "ux_alert_state_symbol_rule"):
            op.create_index(
                "ux_alert_state_symbol_rule",
                "alert_state",
                ["symbol", "rule_code"],
                unique=True,
            )
        if not _has_index(insp, "alert_state", "ix_alert_state_cooldown_until_utc"):
            op.create_index("ix_alert_state_cooldown_until_utc", "alert_state", ["cooldown_until_utc"])

    # =========================
    # 3) alert_deliveries (create if missing)
    # =========================
    insp = sa.inspect(bind)
    if not _has_table(insp, "alert_deliveries"):
        op.create_table(
            "alert_deliveries",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("event_id", sa.Integer, sa.ForeignKey("alert_events.id", ondelete="CASCADE"), nullable=False),
            sa.Column("channel", sa.String(16), nullable=False),
            sa.Column("status", sa.String(16), nullable=False),  # SENT|FAILED|SKIPPED
            sa.Column("attempt_no", sa.Integer, nullable=False, server_default=sa.text("1")),
            sa.Column("sent_at_utc", sa.DateTime(timezone=True), nullable=True),
            sa.Column("response_code", sa.Integer, nullable=True),
            sa.Column("response_meta", sa.JSON, nullable=True),
        )
        op.create_index("ix_alert_deliveries_event_id", "alert_deliveries", ["event_id"])
        op.create_index("ix_alert_deliveries_channel", "alert_deliveries", ["channel"])
        # Use UNIQUE INDEX for (event_id, channel, attempt_no)
        op.create_index(
            "ux_alert_deliveries_event_channel_attempt",
            "alert_deliveries",
            ["event_id", "channel", "attempt_no"],
            unique=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # Drop deliveries table + indexes
    if _has_table(insp, "alert_deliveries"):
        if _has_index(insp, "alert_deliveries", "ux_alert_deliveries_event_channel_attempt"):
            op.drop_index("ux_alert_deliveries_event_channel_attempt", table_name="alert_deliveries")
        if _has_index(insp, "alert_deliveries", "ix_alert_deliveries_channel"):
            op.drop_index("ix_alert_deliveries_channel", table_name="alert_deliveries")
        if _has_index(insp, "alert_deliveries", "ix_alert_deliveries_event_id"):
            op.drop_index("ix_alert_deliveries_event_id", table_name="alert_deliveries")
        op.drop_table("alert_deliveries")

    # Revert alert_state additions (keep table)
    if _has_table(insp, "alert_state"):
        if _has_index(insp, "alert_state", "ux_alert_state_symbol_rule"):
            op.drop_index("ux_alert_state_symbol_rule", table_name="alert_state")
        if _has_index(insp, "alert_state", "ix_alert_state_cooldown_until_utc"):
            op.drop_index("ix_alert_state_cooldown_until_utc", table_name="alert_state")
        with op.batch_alter_table("alert_state", recreate="auto") as batch:
            for col in [
                "last_trading_date",
                "last_mode",
                "last_bucket_ord",
                "last_score_at_fire",
                "last_next_action_code",
                "cooldown_until_utc",
            ]:
                if _has_column(insp, "alert_state", col):
                    batch.drop_column(col)

    # Revert alert_events indexes and added columns (no constraints to drop)
    if _has_table(insp, "alert_events"):
        for ix in [
            "ux_alert_events_code_symbol_date_mode_bucket",
            "ix_alert_events_next_action_code",
            "ix_alert_events_score_at_fire",
            "ix_alert_events_trading_date_rule",
            "ix_alert_events_symbol_trading_date",
            "ix_alert_events_fired_at_utc",
        ]:
            if _has_index(insp, "alert_events", ix):
                op.drop_index(ix, table_name="alert_events")
        with op.batch_alter_table("alert_events", recreate="auto") as batch:
            for col in [
                "severity",
                "digest_bucket",
                "mode",
                "trading_date",
                "bucket_ord",
                "intraday_bucket_label",
                "send_type",
                "digest_id",
                "title_rendered",
                "body_rendered",
                "score_at_fire",
                "next_action_code",
                "triggered_by",
                "profile",
                "config_version",
                "context_json",
                "details_json",
                "channels_summary_json",
                "fired_at_utc",
            ]:
                if _has_column(insp, "alert_events", col):
                    batch.drop_column(col)
