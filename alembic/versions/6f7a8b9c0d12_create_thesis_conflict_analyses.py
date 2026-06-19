"""create_thesis_conflict_analyses

Revision ID: 6f7a8b9c0d12
Revises: 5a6b7c8d9e01
Create Date: 2026-06-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6f7a8b9c0d12"
down_revision: Union[str, Sequence[str], None] = "5a6b7c8d9e01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "thesis_conflict_analyses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("news_item_id", sa.Integer(), nullable=False),
        sa.Column("thesis_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "invalidation_triggered",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["news_item_id"], ["news_items.id"]),
        sa.ForeignKeyConstraint(["thesis_id"], ["investment_theses.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_thesis_conflict_analyses_news_item_id",
        "thesis_conflict_analyses",
        ["news_item_id"],
        unique=False,
    )
    op.create_index(
        "ix_thesis_conflict_analyses_thesis_id",
        "thesis_conflict_analyses",
        ["thesis_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_thesis_conflict_analyses_thesis_id",
        table_name="thesis_conflict_analyses",
    )
    op.drop_index(
        "ix_thesis_conflict_analyses_news_item_id",
        table_name="thesis_conflict_analyses",
    )
    op.drop_table("thesis_conflict_analyses")
