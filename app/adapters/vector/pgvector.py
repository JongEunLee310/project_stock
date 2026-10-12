from dataclasses import asdict

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.adapters.vector.base import VectorStore
from app.adapters.vector.types import ChunkFilter, ChunkHit, ChunkRecord
from app.domains.rag.model import DocumentChunk
from app.domains.rag.types import ChunkContentQuality, ChunkSourceType


class PgVectorStore(VectorStore):
    def __init__(self, db: Session) -> None:
        self.db = db

    def upsert(self, records: list[ChunkRecord]) -> int:
        for record in records:
            values = asdict(record)
            values["source_type"] = record.source_type.value
            values["content_quality"] = record.content_quality.value
            stmt = insert(DocumentChunk).values(**values)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_document_chunks_source_chunk_model",
                set_={name: getattr(stmt.excluded, name) for name in values},
            )
            self.db.execute(stmt)
        self.db.flush()
        return len(records)

    def delete_by_source(self, source_type: ChunkSourceType, source_id: int) -> int:
        stmt = (
            delete(DocumentChunk)
            .where(
                DocumentChunk.source_type == source_type.value,
                DocumentChunk.source_id == source_id,
            )
            .returning(DocumentChunk.id)
        )
        ids = self.db.scalars(stmt).all()
        self.db.flush()
        return len(ids)

    def get_content_hashes(
        self, source_type: ChunkSourceType, source_ids: list[int], embedding_model: str
    ) -> dict[int, str]:
        if not source_ids:
            return {}
        rows = self.db.execute(
            select(DocumentChunk.source_id, DocumentChunk.content_hash).where(
                DocumentChunk.source_type == source_type.value,
                DocumentChunk.source_id.in_(source_ids),
                DocumentChunk.embedding_model == embedding_model,
            )
        ).all()
        return {source_id: content_hash for source_id, content_hash in rows}

    def search(
        self, query_vector: list[float], filters: ChunkFilter, k: int
    ) -> list[ChunkHit]:
        if k <= 0:
            return []
        distance = DocumentChunk.embedding.cosine_distance(query_vector)
        stmt = select(DocumentChunk, distance).where(
            DocumentChunk.embedding_model == filters.embedding_model
        )
        if filters.asset_id is not None:
            stmt = stmt.where(DocumentChunk.asset_ids.contains([filters.asset_id]))
        if filters.source_types:
            stmt = stmt.where(
                DocumentChunk.source_type.in_(
                    [source_type.value for source_type in filters.source_types]
                )
            )
        if filters.published_after is not None:
            stmt = stmt.where(DocumentChunk.published_at > filters.published_after)
        if filters.published_before is not None:
            stmt = stmt.where(DocumentChunk.published_at < filters.published_before)
        stmt = stmt.order_by(distance, DocumentChunk.id).limit(k)
        rows = self.db.execute(stmt.execution_options(populate_existing=True)).all()
        return [
            ChunkHit(
                chunk_id=chunk.id,
                source_type=ChunkSourceType(chunk.source_type),
                source_id=chunk.source_id,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                content_quality=ChunkContentQuality(chunk.content_quality),
                published_at=chunk.published_at,
                score=1.0 - float(cosine_distance),
            )
            for chunk, cosine_distance in rows
        ]
