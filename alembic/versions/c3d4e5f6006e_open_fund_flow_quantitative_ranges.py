"""open fund flow quantitative ranges

Revision ID: c3d4e5f6006e
Revises: c3d4e5f6006d
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "c3d4e5f6006e"
down_revision: str | None = "c3d4e5f6006d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "fund_flow_outlooks",
        sa.Column(
            "estimated_flow_low",
            sa.Numeric(precision=20, scale=4),
            nullable=True,
        ),
    )
    op.add_column(
        "fund_flow_outlooks",
        sa.Column(
            "estimated_flow_high",
            sa.Numeric(precision=20, scale=4),
            nullable=True,
        ),
    )
    op.add_column(
        "fund_flow_outlooks",
        sa.Column("estimated_flow_currency", sa.String(length=10), nullable=True),
    )
    op.drop_column("fund_flow_outlooks", "estimated_range")

    op.add_column(
        "fund_flow_scenarios",
        sa.Column(
            "expected_net_flow_low",
            sa.Numeric(precision=20, scale=4),
            nullable=True,
        ),
    )
    op.add_column(
        "fund_flow_scenarios",
        sa.Column(
            "expected_net_flow_high",
            sa.Numeric(precision=20, scale=4),
            nullable=True,
        ),
    )
    op.add_column(
        "fund_flow_scenarios",
        sa.Column(
            "expected_net_flow_currency",
            sa.String(length=10),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.add_column(
        "fund_flow_outlooks",
        sa.Column("estimated_range", sa.String(length=100), nullable=True),
    )
    op.drop_column("fund_flow_scenarios", "expected_net_flow_currency")
    op.drop_column("fund_flow_scenarios", "expected_net_flow_high")
    op.drop_column("fund_flow_scenarios", "expected_net_flow_low")
    op.drop_column("fund_flow_outlooks", "estimated_flow_currency")
    op.drop_column("fund_flow_outlooks", "estimated_flow_high")
    op.drop_column("fund_flow_outlooks", "estimated_flow_low")
