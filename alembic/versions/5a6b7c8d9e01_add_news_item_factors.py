"""add_news_item_factors

Revision ID: 5a6b7c8d9e01
Revises: 4d5e6f708192
Create Date: 2026-06-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5a6b7c8d9e01"
down_revision: Union[str, Sequence[str], None] = "4d5e6f708192"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("news_items", sa.Column("positive_factors", sa.Text(), nullable=True))
    op.add_column("news_items", sa.Column("negative_factors", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("news_items", "negative_factors")
    op.drop_column("news_items", "positive_factors")
