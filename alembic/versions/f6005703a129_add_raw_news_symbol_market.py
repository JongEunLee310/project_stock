"""add_raw_news_symbol_market

Revision ID: f6005703a129
Revises: e5f6005702
Create Date: 2026-07-02 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f6005703a129"
down_revision: Union[str, Sequence[str], None] = "e5f6005702"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "raw_news_events",
        sa.Column("symbol", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "raw_news_events",
        sa.Column("market", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("raw_news_events", "market")
    op.drop_column("raw_news_events", "symbol")
