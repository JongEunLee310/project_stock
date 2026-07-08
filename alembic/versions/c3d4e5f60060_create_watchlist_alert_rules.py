"""create_watchlist_alert_rules

Revision ID: c3d4e5f60060
Revises: c3d4e5f60059
Create Date: 2026-07-08 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "c3d4e5f60060"
down_revision: str | Sequence[str] | None = "c3d4e5f60059"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "watchlist_alert_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("watchlist_id", sa.Integer(), sa.ForeignKey("watchlists.id"), nullable=False),
        sa.Column("template_type", sa.String(50), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
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
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "watchlist_id",
            "template_type",
            name="uq_watchlist_alert_rules_template",
        ),
    )
    op.create_index(
        "ix_watchlist_alert_rules_watchlist_id",
        "watchlist_alert_rules",
        ["watchlist_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_watchlist_alert_rules_watchlist_id",
        table_name="watchlist_alert_rules",
    )
    op.drop_table("watchlist_alert_rules")
