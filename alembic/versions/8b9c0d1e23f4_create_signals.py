"""create_signals

Revision ID: 8b9c0d1e23f4
Revises: 7a8b9c0d1e23
Create Date: 2026-06-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8b9c0d1e23f4"
down_revision: Union[str, Sequence[str], None] = "7a8b9c0d1e23"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "signals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("thesis_id", sa.Integer(), nullable=True),
        sa.Column("news_item_id", sa.Integer(), nullable=True),
        sa.Column("signal_type", sa.String(length=20), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("risk_level", sa.String(length=20), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["news_item_id"], ["news_items.id"]),
        sa.ForeignKeyConstraint(["thesis_id"], ["investment_theses.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_signals_asset_id", "signals", ["asset_id"], unique=False)
    op.create_index(
        "ix_signals_signal_type",
        "signals",
        ["signal_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_signals_signal_type", table_name="signals")
    op.drop_index("ix_signals_asset_id", table_name="signals")
    op.drop_table("signals")
