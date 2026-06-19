"""create_research_reports

Revision ID: 7a8b9c0d1e23
Revises: 6f7a8b9c0d12
Create Date: 2026-06-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7a8b9c0d1e23"
down_revision: Union[str, Sequence[str], None] = "6f7a8b9c0d12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "research_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("thesis_id", sa.Integer(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("positive_factors", sa.Text(), nullable=True),
        sa.Column("negative_factors", sa.Text(), nullable=True),
        sa.Column("risk_level", sa.String(length=20), nullable=True),
        sa.Column("thesis_conflict_status", sa.String(length=20), nullable=True),
        sa.Column("conflict_reason", sa.Text(), nullable=True),
        sa.Column("news_item_ids", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["thesis_id"], ["investment_theses.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_research_reports_asset_id",
        "research_reports",
        ["asset_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_research_reports_asset_id", table_name="research_reports")
    op.drop_table("research_reports")
