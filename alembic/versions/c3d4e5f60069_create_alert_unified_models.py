"""create alert unified models

Revision ID: c3d4e5f60069
Revises: c3d4e5f60068
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "c3d4e5f60069"
down_revision: str | None = "c3d4e5f60068"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alert_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("template_type", sa.String(length=50), nullable=True),
        sa.Column("target_type", sa.String(length=20), nullable=False),
        sa.Column("target_id", sa.String(length=255), nullable=True),
        sa.Column("condition", sa.JSON(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("channels", sa.JSON(), nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("cooldown_seconds", sa.Integer(), nullable=False),
        sa.Column("delivery_policy", sa.String(length=30), nullable=False),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alert_rules_enabled", "alert_rules", ["enabled"])
    op.create_index("ix_alert_rules_user_id", "alert_rules", ["user_id"])

    op.create_table(
        "alert_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("rule_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("target_type", sa.String(length=20), nullable=False),
        sa.Column("target_id", sa.String(length=255), nullable=True),
        sa.Column("asset_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("triggered_value", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("dedup_key", sa.String(length=255), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "triggered_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["rule_id"], ["alert_rules.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "dedup_key",
            name="uq_alert_events_user_dedup",
        ),
    )
    op.create_index("ix_alert_events_asset_id", "alert_events", ["asset_id"])
    op.create_index("ix_alert_events_dedup_key", "alert_events", ["dedup_key"])
    op.create_index("ix_alert_events_rule_id", "alert_events", ["rule_id"])
    op.create_index(
        "ix_alert_events_triggered_at",
        "alert_events",
        ["triggered_at"],
    )
    op.create_index("ix_alert_events_user_id", "alert_events", ["user_id"])

    op.create_table(
        "alert_deliveries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("alert_event_id", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column(
            "attempted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(["alert_event_id"], ["alert_events.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_alert_deliveries_alert_event_id",
        "alert_deliveries",
        ["alert_event_id"],
    )

    op.create_table(
        "notification_channels",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("channel_type", sa.String(length=20), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notification_channels_user_id",
        "notification_channels",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_notification_channels_user_id",
        table_name="notification_channels",
    )
    op.drop_table("notification_channels")

    op.drop_index(
        "ix_alert_deliveries_alert_event_id",
        table_name="alert_deliveries",
    )
    op.drop_table("alert_deliveries")

    op.drop_index("ix_alert_events_user_id", table_name="alert_events")
    op.drop_index("ix_alert_events_triggered_at", table_name="alert_events")
    op.drop_index("ix_alert_events_rule_id", table_name="alert_events")
    op.drop_index("ix_alert_events_dedup_key", table_name="alert_events")
    op.drop_index("ix_alert_events_asset_id", table_name="alert_events")
    op.drop_table("alert_events")

    op.drop_index("ix_alert_rules_user_id", table_name="alert_rules")
    op.drop_index("ix_alert_rules_enabled", table_name="alert_rules")
    op.drop_table("alert_rules")
