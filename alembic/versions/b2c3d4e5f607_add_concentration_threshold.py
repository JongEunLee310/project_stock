"""add_concentration_threshold

Revision ID: b2c3d4e5f607
Revises: a1b2c3d4e5f6
Create Date: 2026-06-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f607"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "portfolios",
        sa.Column(
            "concentration_threshold",
            sa.Numeric(5, 4),
            server_default="0.4",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("portfolios", "concentration_threshold")
