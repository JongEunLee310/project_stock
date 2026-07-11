"""add_news_item_category

Revision ID: c3d4e5f60064
Revises: c3d4e5f60063
Create Date: 2026-07-11 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "c3d4e5f60064"
down_revision: str | Sequence[str] | None = "c3d4e5f60063"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "news_items",
        sa.Column("category", sa.String(length=30), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("news_items", "category")
