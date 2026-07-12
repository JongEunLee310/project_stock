"""create earnings reports

Revision ID: c3d4e5f60066
Revises: c3d4e5f60065
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "c3d4e5f60066"
down_revision: str | None = "c3d4e5f60065"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "earnings_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("market", sa.String(length=20), nullable=False),
        sa.Column("period", sa.String(length=10), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("revenue", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column(
            "operating_income", sa.Numeric(precision=20, scale=4), nullable=True
        ),
        sa.Column("eps", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("eps_estimate", sa.Numeric(precision=20, scale=4), nullable=True),
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
            "period",
            name="uq_earnings_reports_symbol_market_period",
        ),
    )


def downgrade() -> None:
    op.drop_table("earnings_reports")
