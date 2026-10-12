"""add daily brief report fields

Revision ID: c3d4e5f60071
Revises: c3d4e5f60070
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f60071"
down_revision: str | None = "c3d4e5f60070"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "research_reports",
        sa.Column(
            "report_type", sa.String(20), server_default="ARTICLE", nullable=False
        ),
    )
    op.add_column("research_reports", sa.Column("brief_date", sa.Date(), nullable=True))
    op.add_column("research_reports", sa.Column("content", sa.JSON(), nullable=True))
    op.create_index(
        "uq_research_reports_daily_brief",
        "research_reports",
        ["asset_id", "brief_date"],
        unique=True,
        postgresql_where=sa.text("report_type = 'DAILY_BRIEF'"),
        sqlite_where=sa.text("report_type = 'DAILY_BRIEF'"),
    )


def downgrade() -> None:
    op.drop_index("uq_research_reports_daily_brief", table_name="research_reports")
    op.drop_column("research_reports", "content")
    op.drop_column("research_reports", "brief_date")
    op.drop_column("research_reports", "report_type")
