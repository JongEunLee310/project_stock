"""add_trust_level_content_hash_to_news_items

Revision ID: c3d4e5f60059
Revises: c3d4e5f60058
Create Date: 2026-07-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3d4e5f60059"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f60058"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("news_items", sa.Column("trust_level", sa.String(length=20), nullable=True))
    op.add_column("news_items", sa.Column("content_hash", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("news_items", "content_hash")
    op.drop_column("news_items", "trust_level")
