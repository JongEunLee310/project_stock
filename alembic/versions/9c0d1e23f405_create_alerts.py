"""create_alerts

Revision ID: 9c0d1e23f405
Revises: 8b9c0d1e23f4
Create Date: 2026-06-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9c0d1e23f405"
down_revision: Union[str, Sequence[str], None] = "8b9c0d1e23f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("signal_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="UNREAD",
            nullable=False,
        ),
        sa.Column("dedup_key", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["signal_id"], ["signals.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "dedup_key", name="uq_alerts_user_dedup"),
    )
    op.create_index("ix_alerts_signal_id", "alerts", ["signal_id"], unique=False)
    op.create_index("ix_alerts_user_id", "alerts", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_alerts_user_id", table_name="alerts")
    op.drop_index("ix_alerts_signal_id", table_name="alerts")
    op.drop_table("alerts")
