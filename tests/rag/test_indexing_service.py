from datetime import datetime
from unittest.mock import Mock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.embedding.exceptions import EmbeddingError
from app.adapters.embedding.mock import MockEmbedder
from app.adapters.vector.memory import InMemoryVectorStore
from app.adapters.vector.types import ChunkFilter
from app.domains.assets.model import Asset
from app.domains.news.repository import NewsItemRepository
from app.domains.news.schema import NewsItemCreate
from app.domains.rag.indexing import compose_embedding_text, embedding_input_hash
from app.domains.rag.indexing_service import EmbeddingIndexer
from app.domains.rag.model import DocumentChunk
from app.domains.rag.types import ChunkContentQuality, ChunkSourceType
from app.domains.raw_news.model import RawNewsEvent
from app.domains.raw_news.repository import RawNewsEventRepository
from app.domains.raw_news.schema import RawNewsEventCreate


class CountingEmbedder(MockEmbedder):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[list[str]] = []
        self.error: Exception | None = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        if self.error:
            raise self.error
        return super().embed(texts)


def create_event(db: Session, index: int, body: str | None = None) -> RawNewsEvent:
    event = RawNewsEventRepository(db).create_or_skip(
        RawNewsEventCreate(
            title=f"뉴스 {index}",
            url=f"https://example.com/{index}",
            source="test",
            body=body,
        )
    )
    assert event is not None
    return event


def test_repository_to_indexer_to_asset_search(db: Session) -> None:
    assets = [
        Asset(symbol=symbol, name=symbol, market="NASDAQ") for symbol in ["A", "B"]
    ]
    db.add_all(assets)
    db.commit()
    event = create_event(db, 1, "본문" * 1600)
    event.published_at = datetime(2026, 10, 10)
    db.commit()
    summary_event = create_event(db, 2, "짧은 본문")
    title_event = create_event(db, 3)
    repo = NewsItemRepository(db)
    for asset in [assets[1], assets[0], assets[0]]:
        repo.create(
            NewsItemCreate(
                raw_news_event_id=event.id,
                asset_id=asset.id,
                title=event.title,
                url=event.url,
                source=event.source,
                summary="무시할 요약",
            )
        )
    for summary in [" ", "첫 요약", "다른 요약"]:
        repo.create(
            NewsItemCreate(
                raw_news_event_id=summary_event.id,
                asset_id=assets[0].id,
                title=summary_event.title,
                url=summary_event.url,
                source=summary_event.source,
                summary=summary,
            )
        )
    store = InMemoryVectorStore()
    embedder = CountingEmbedder()
    indexer = EmbeddingIndexer(db, embedder, store)
    result = indexer.run(scan_page_size=2)
    assert (result.scanned, result.embedded_documents, result.chunks_written) == (
        3,
        3,
        5,
    )
    assert not result.has_more
    assert len(embedder.calls) == 1
    query = embedder.embed(["뉴스"])[0]
    hits = store.search(query, ChunkFilter(embedder.model_name), 20)
    full = [hit for hit in hits if hit.source_id == event.id]
    assert len(full) == 3
    assert all(hit.content_quality == ChunkContentQuality.FULL for hit in full)
    assert all(hit.published_at == event.published_at for hit in full)
    for asset in assets:
        assert event.id in {
            hit.source_id
            for hit in store.search(
                query, ChunkFilter(embedder.model_name, asset_id=asset.id), 20
            )
        }
    summary_hit = next(hit for hit in hits if hit.source_id == summary_event.id)
    assert summary_hit.content == "뉴스 2\n\n짧은 본문\n\n첫 요약"
    assert summary_hit.content_quality == ChunkContentQuality.SUMMARY
    title_hit = next(hit for hit in hits if hit.source_id == title_event.id)
    assert title_hit.content_quality == ChunkContentQuality.TITLE_ONLY
    assert title_hit.published_at == title_event.collected_at
    stored = [record for _, record in store._records.values()]
    assert all(
        record.asset_ids == sorted(asset.id for asset in assets)
        for record in stored
        if record.source_id == event.id
    )
    assert (
        next(
            record.asset_ids for record in stored if record.source_id == title_event.id
        )
        == []
    )
    calls = len(embedder.calls)
    again = indexer.run(scan_page_size=1)
    assert (again.embedded_documents, again.unchanged, again.scanned) == (0, 3, 3)
    assert len(embedder.calls) == calls
    assert store.search(query, ChunkFilter(embedder.model_name), 20) == hits
    event.body = "수정 본문" * 100
    db.commit()
    updated = indexer.run()
    assert (updated.embedded_documents, updated.unchanged, updated.chunks_written) == (
        1,
        2,
        1,
    )
    updated_hits = store.search(query, ChunkFilter(embedder.model_name), 20)
    assert len(updated_hits) == 3
    assert [hit for hit in updated_hits if hit.source_id != event.id] == [
        hit for hit in hits if hit.source_id != event.id
    ]


def test_batch_limit_and_scanning_unchanged_pages(db: Session) -> None:
    events = [create_event(db, index) for index in range(5)]
    store = InMemoryVectorStore()
    indexer = EmbeddingIndexer(db, CountingEmbedder(), store)
    first = indexer.run(max_documents=2, scan_page_size=1)
    assert (first.scanned, first.embedded_documents, first.has_more) == (2, 2, True)
    second = indexer.run(max_documents=2, scan_page_size=2)
    assert (
        second.scanned,
        second.unchanged,
        second.embedded_documents,
        second.has_more,
    ) == (4, 2, 2, True)
    third = indexer.run(max_documents=2, scan_page_size=1)
    assert (
        third.scanned,
        third.unchanged,
        third.embedded_documents,
        third.has_more,
    ) == (5, 4, 1, False)
    assert set(
        store.get_content_hashes(
            ChunkSourceType.NEWS, [e.id for e in events], "mock-embedding"
        )
    ) == {e.id for e in events}


def test_embedding_failure_preserves_existing_batch_and_retries(db: Session) -> None:
    first = create_event(db, 1, "본문" * 1000)
    store = InMemoryVectorStore()
    embedder = CountingEmbedder()
    indexer = EmbeddingIndexer(db, embedder, store)
    indexer.run()
    original = dict(store._records)
    first.body = "바뀐 본문"
    db.commit()
    create_event(db, 2)
    embedder.error = EmbeddingError("endpoint unavailable")
    commit = Mock(wraps=db.commit)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(db, "commit", commit)
        with pytest.raises(EmbeddingError, match="endpoint unavailable"):
            indexer.run()
    commit.assert_not_called()
    assert store._records == original
    assert db.scalars(select(DocumentChunk)).all() == []
    assert RawNewsEventRepository(db).list_after_id(0, 10)[0].body == "바뀐 본문"
    embedder.error = None
    assert indexer.run().embedded_documents == 2


def test_summary_changes_reindex_only_when_used(db: Session) -> None:
    asset = Asset(symbol="A", name="A", market="NASDAQ")
    db.add(asset)
    db.commit()
    event = create_event(db, 1)
    item = NewsItemRepository(db).create(
        NewsItemCreate(
            raw_news_event_id=event.id,
            asset_id=asset.id,
            title=event.title,
            url=event.url,
            source=event.source,
            summary="요약",
        )
    )
    store = InMemoryVectorStore()
    indexer = EmbeddingIndexer(db, CountingEmbedder(), store)
    indexer.run()
    item.summary = "새 요약"
    db.commit()
    assert indexer.run().embedded_documents == 1
    expected, _ = compose_embedding_text(event.title, event.body, item.summary)
    assert store.get_content_hashes(
        ChunkSourceType.NEWS, [event.id], "mock-embedding"
    ) == {event.id: embedding_input_hash(expected)}


@pytest.mark.parametrize(("max_documents", "scan_page_size"), [(0, 1), (1, 0), (-1, 1)])
def test_invalid_limits(db: Session, max_documents: int, scan_page_size: int) -> None:
    with pytest.raises(ValueError):
        EmbeddingIndexer(db, CountingEmbedder(), InMemoryVectorStore()).run(
            max_documents, scan_page_size
        )
