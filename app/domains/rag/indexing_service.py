from dataclasses import dataclass, replace
from datetime import datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.adapters.embedding.base import Embedder
from app.adapters.embedding.exceptions import EmbeddingError
from app.adapters.vector.base import VectorStore
from app.adapters.vector.types import ChunkRecord
from app.domains.knowledge.repository import KnowledgeDocumentRepository
from app.domains.news.model import NewsItem
from app.domains.news.repository import NewsItemRepository
from app.domains.rag.indexing import (
    chunk_text,
    compose_embedding_text,
    embedding_input_hash,
)
from app.domains.rag.types import ChunkContentQuality, ChunkSourceType
from app.domains.raw_news.repository import RawNewsEventRepository


@dataclass(frozen=True)
class IndexingResult:
    scanned: int
    embedded_documents: int
    chunks_written: int
    unchanged: int
    has_more: bool


class EmbeddingIndexer:
    def __init__(
        self, db: Session, embedder: Embedder, vector_store: VectorStore
    ) -> None:
        self.db = db
        self.embedder = embedder
        self.vector_store = vector_store

    def run(
        self, max_documents: int = 100, scan_page_size: int = 500
    ) -> IndexingResult:
        if max_documents <= 0 or scan_page_size <= 0:
            raise ValueError("document and page limits must be positive")
        raw_repo = RawNewsEventRepository(self.db)
        news_repo = NewsItemRepository(self.db)
        scanned = unchanged = documents = 0
        after_id = 0
        records: list[ChunkRecord] = []
        sources: list[tuple[ChunkSourceType, int]] = []
        while documents < max_documents:
            page = raw_repo.list_after_id(after_id, scan_page_size)
            if not page:
                break
            ids = [event.id for event in page]
            hashes = self.vector_store.get_content_hashes(
                ChunkSourceType.NEWS, ids, self.embedder.model_name
            )
            linked: dict[int, list[NewsItem]] = {}
            for item in news_repo.list_by_raw_event_ids(ids):
                if item.raw_news_event_id is not None:
                    linked.setdefault(item.raw_news_event_id, []).append(item)
            for event in page:
                scanned += 1
                items = linked.get(event.id, [])
                summary = next(
                    (
                        item.summary
                        for item in items
                        if item.summary and item.summary.strip()
                    ),
                    None,
                )
                text, quality = compose_embedding_text(event.title, event.body, summary)
                content_hash = embedding_input_hash(text)
                if hashes.get(event.id) == content_hash:
                    unchanged += 1
                    continue
                documents += 1
                sources.append((ChunkSourceType.NEWS, event.id))
                asset_ids = sorted({item.asset_id for item in items})
                records.extend(
                    ChunkRecord(
                        source_type=ChunkSourceType.NEWS,
                        source_id=event.id,
                        chunk_index=index,
                        content=content,
                        content_quality=quality,
                        embedding=[],
                        embedding_model=self.embedder.model_name,
                        asset_ids=asset_ids,
                        published_at=event.published_at or event.collected_at,
                        content_hash=content_hash,
                    )
                    for index, content in enumerate(chunk_text(text))
                )
                if documents == max_documents:
                    break
            after_id = page[-1].id
        knowledge_repo = KnowledgeDocumentRepository(self.db)
        after_id = 0
        while documents < max_documents:
            knowledge_page = knowledge_repo.list_after_id(after_id, scan_page_size)
            if not knowledge_page:
                break
            hashes = self.vector_store.get_content_hashes(
                ChunkSourceType.KNOWLEDGE,
                [document.id for document in knowledge_page],
                self.embedder.model_name,
            )
            for document in knowledge_page:
                scanned += 1
                text = document.title + "\n\n" + document.content
                content_hash = embedding_input_hash(text)
                if hashes.get(document.id) == content_hash:
                    unchanged += 1
                    continue
                documents += 1
                sources.append((ChunkSourceType.KNOWLEDGE, document.id))
                published_at = (
                    datetime.combine(
                        document.effective_date, time(), ZoneInfo("Asia/Seoul")
                    )
                    if document.effective_date is not None
                    else document.created_at
                )
                records.extend(
                    ChunkRecord(
                        source_type=ChunkSourceType.KNOWLEDGE,
                        source_id=document.id,
                        chunk_index=index,
                        content=content,
                        content_quality=ChunkContentQuality.FULL,
                        embedding=[],
                        embedding_model=self.embedder.model_name,
                        asset_ids=[document.asset_id]
                        if document.asset_id is not None
                        else [],
                        published_at=published_at,
                        content_hash=content_hash,
                    )
                    for index, content in enumerate(chunk_text(text))
                )
                if documents == max_documents:
                    break
            after_id = knowledge_page[-1].id
        if sources:
            vectors = self.embedder.embed([record.content for record in records])
            # Validate the batch before deleting any existing chunks.
            if len(vectors) != len(records) or any(
                len(vector) != self.embedder.dimensions for vector in vectors
            ):
                raise EmbeddingError("embedding batch shape mismatch")
            records = [
                replace(record, embedding=vector)
                for record, vector in zip(records, vectors, strict=True)
            ]
            for source_type, source_id in sources:
                self.vector_store.delete_by_source(source_type, source_id)
                self.vector_store.upsert(
                    [
                        record
                        for record in records
                        if record.source_type == source_type
                        and record.source_id == source_id
                    ]
                )
            self.db.commit()
        return IndexingResult(
            scanned, documents, len(records), unchanged, documents == max_documents
        )
