"""create_stock_price_bars

Revision ID: c3d4e5f60056
Revises: c3d4e5f60055
Create Date: 2026-06-25 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3d4e5f60056"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f60055"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "stock_price_bars",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("market", sa.String(length=20), nullable=False),
        sa.Column("interval", sa.String(length=10), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open_price", sa.Numeric(20, 4), nullable=False),
        sa.Column("high_price", sa.Numeric(20, 4), nullable=False),
        sa.Column("low_price", sa.Numeric(20, 4), nullable=False),
        sa.Column("close_price", sa.Numeric(20, 4), nullable=False),
        sa.Column("adjusted_close_price", sa.Numeric(20, 4), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "symbol",
            "market",
            "interval",
            "timestamp",
            name="uq_price_bars_symbol_market_interval_ts",
        ),
    )


def downgrade() -> None:
    op.drop_table("stock_price_bars")
