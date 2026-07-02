"""add_raw_processing_status

Revision ID: c3d4e5f60058
Revises: c3d4e5f60057
Create Date: 2026-07-02 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.domains.ingestion.schema import ProcessingStatus


# revision identifiers, used by Alembic.
revision: str = "c3d4e5f60058"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f60057"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "raw_prices",
        sa.Column(
            "processing_status",
            sa.String(length=20),
            server_default=ProcessingStatus.FETCHED.value,
            nullable=False,
        ),
    )
    op.create_index(
        "ix_raw_prices_processing_status",
        "raw_prices",
        ["processing_status"],
        unique=False,
    )
    op.add_column(
        "raw_news_events",
        sa.Column(
            "processing_status",
            sa.String(length=20),
            server_default=ProcessingStatus.FETCHED.value,
            nullable=False,
        ),
    )
    op.create_index(
        "ix_raw_news_events_processing_status",
        "raw_news_events",
        ["processing_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_raw_news_events_processing_status",
        table_name="raw_news_events",
    )
    op.drop_column("raw_news_events", "processing_status")
    op.drop_index(
        "ix_raw_prices_processing_status",
        table_name="raw_prices",
    )
    op.drop_column("raw_prices", "processing_status")
