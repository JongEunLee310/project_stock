from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    DateTime,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domains.rag.types import EMBEDDING_DIMENSIONS


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint(
            "source_type",
            "source_id",
            "chunk_index",
            "embedding_model",
            name="uq_document_chunks_source_chunk_model",
        ),
        Index(
            "ix_document_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ).ddl_if(dialect="postgresql"),
        Index(
            "ix_document_chunks_asset_ids",
            "asset_ids",
            postgresql_using="gin",
        ).ddl_if(dialect="postgresql"),
        Index("ix_document_chunks_published_at", "published_at"),
        Index("ix_document_chunks_source", "source_type", "source_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_type: Mapped[str] = mapped_column(String(20))
    source_id: Mapped[int] = mapped_column(Integer)
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    content_quality: Mapped[str] = mapped_column(String(20))
    embedding: Mapped[list[float]] = mapped_column(
        Vector(EMBEDDING_DIMENSIONS).with_variant(JSON, "sqlite")
    )
    embedding_model: Mapped[str] = mapped_column(String(100))
    asset_ids: Mapped[list[int]] = mapped_column(
        ARRAY(Integer).with_variant(JSON, "sqlite"), default=list
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
