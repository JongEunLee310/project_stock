"""add knowledge documents

Revision ID: c3d4e5f60072
Revises: c3d4e5f60071
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f60072"
down_revision: str | None = "c3d4e5f60071"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("asset_id", sa.Integer(), sa.ForeignKey("assets.id"), nullable=True),
        sa.Column("source_name", sa.String(100), nullable=False),
        sa.Column("source_url", sa.String(1000), nullable=False),
        sa.Column("license_note", sa.String(255), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("external_id", sa.String(200), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column(
            "metadata", sa.JSON(), server_default=sa.text("'{}'"), nullable=False
        ),
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
        sa.UniqueConstraint(
            "kind", "external_id", name="uq_knowledge_documents_kind_external_id"
        ),
    )
    op.create_index(
        "ix_knowledge_documents_asset_kind_effective_date",
        "knowledge_documents",
        ["asset_id", "kind", "effective_date"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_knowledge_documents_asset_kind_effective_date",
        table_name="knowledge_documents",
    )
    op.drop_table("knowledge_documents")
