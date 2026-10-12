"""create document chunks

Revision ID: c3d4e5f6006f
Revises: c3d4e5f6006e

다른 객체가 의존할 수 있으므로 downgrade에서 vector 확장은 제거하지 않는다.
"""

from collections.abc import Sequence

from alembic import op
from pgvector.sqlalchemy import Vector
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY

revision: str = "c3d4e5f6006f"
down_revision: str | None = "c3d4e5f6006e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_quality", sa.String(20), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column("embedding_model", sa.String(100), nullable=False),
        sa.Column(
            "asset_ids",
            ARRAY(sa.Integer()),
            nullable=False,
            server_default=sa.text("'{}'::integer[]"),
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "source_type",
            "source_id",
            "chunk_index",
            "embedding_model",
            name="uq_document_chunks_source_chunk_model",
        ),
    )
    op.create_index(
        "ix_document_chunks_embedding",
        "document_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(
        "ix_document_chunks_asset_ids",
        "document_chunks",
        ["asset_ids"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_document_chunks_published_at", "document_chunks", ["published_at"]
    )
    op.create_index(
        "ix_document_chunks_source", "document_chunks", ["source_type", "source_id"]
    )


def downgrade() -> None:
    op.drop_table("document_chunks")
