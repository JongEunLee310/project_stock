"""add_asset_detail_fields

Revision ID: c3d4e5f60051
Revises: c3d4e5f60050
Create Date: 2026-06-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3d4e5f60051"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f60050"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("assets", sa.Column("sector", sa.String(length=100), nullable=True))
    op.add_column("assets", sa.Column("industry", sa.String(length=100), nullable=True))
    op.add_column("assets", sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("assets", "description")
    op.drop_column("assets", "industry")
    op.drop_column("assets", "sector")
