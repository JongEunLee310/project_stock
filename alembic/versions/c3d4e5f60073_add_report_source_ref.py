"""add report source reference

Revision ID: c3d4e5f60073
Revises: c3d4e5f60072
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f60073"
down_revision: str | None = "c3d4e5f60072"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "research_reports", sa.Column("source_ref", sa.String(200), nullable=True)
    )
    op.create_index(
        "uq_research_reports_source_ref",
        "research_reports",
        ["asset_id", "report_type", "source_ref"],
        unique=True,
        postgresql_where=sa.text("source_ref IS NOT NULL"),
        sqlite_where=sa.text("source_ref IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_research_reports_source_ref", table_name="research_reports")
    op.drop_column("research_reports", "source_ref")
