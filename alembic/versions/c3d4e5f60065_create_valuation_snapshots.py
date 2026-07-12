"""create valuation snapshots

Revision ID: c3d4e5f60065
Revises: c3d4e5f60064
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "c3d4e5f60065"
down_revision: str | None = "c3d4e5f60064"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "valuation_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("market", sa.String(length=20), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("per", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("forward_per", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("psr", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("pbr", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("ev_ebitda", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("peg", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("fcf_yield", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "symbol",
            "market",
            "as_of",
            name="uq_valuation_snapshots_symbol_market_as_of",
        ),
    )


def downgrade() -> None:
    op.drop_table("valuation_snapshots")
