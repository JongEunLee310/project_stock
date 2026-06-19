"""add_portfolio_cash_balance

Revision ID: c3d4e5f60054
Revises: c3d4e5f60053
Create Date: 2026-06-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3d4e5f60054"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f60053"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "portfolios",
        sa.Column(
            "cash_balance",
            sa.Numeric(20, 4),
            server_default="0",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("portfolios", "cash_balance")
