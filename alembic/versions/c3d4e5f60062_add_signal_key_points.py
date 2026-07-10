"""add_signal_key_points

Revision ID: c3d4e5f60062
Revises: c3d4e5f60061
Create Date: 2026-07-10 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "c3d4e5f60062"
down_revision: str | Sequence[str] | None = "c3d4e5f60061"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("signals", sa.Column("key_points", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("signals", "key_points")
