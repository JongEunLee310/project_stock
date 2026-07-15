"""create research summaries

Revision ID: c3d4e5f60068
Revises: c3d4e5f60067
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "c3d4e5f60068"
down_revision: str | None = "c3d4e5f60067"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_summaries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("stance", sa.String(length=50), nullable=False),
        sa.Column("stance_confidence", sa.String(length=20), nullable=False),
        sa.Column("stance_comment", sa.Text(), nullable=True),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("positive_factors", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("caution_factors", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("next_checks", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("counter_points", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("confidence_basis", sa.Text(), nullable=True),
        sa.Column("key_risks", sa.JSON(), nullable=False),
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
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_id", name="uq_research_summaries_asset"),
    )


def downgrade() -> None:
    op.drop_table("research_summaries")
