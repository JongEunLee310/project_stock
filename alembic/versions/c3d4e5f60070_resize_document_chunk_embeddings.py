"""resize document chunk embeddings

Revision ID: c3d4e5f60070
Revises: c3d4e5f6006f

차원이 달라 변환할 수 없는 청크는 삭제하며, 원본에서 다시 만들 수 있다.
"""

from collections.abc import Sequence

from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "c3d4e5f60070"
down_revision: str | None = "c3d4e5f6006f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _resize_embedding(dimensions: int) -> None:
    op.drop_index("ix_document_chunks_embedding", table_name="document_chunks")
    op.execute("DELETE FROM document_chunks")
    op.alter_column("document_chunks", "embedding", type_=Vector(dimensions))
    op.create_index(
        "ix_document_chunks_embedding",
        "document_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def upgrade() -> None:
    _resize_embedding(1024)


def downgrade() -> None:
    _resize_embedding(1536)
