from datetime import date, timedelta
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from app.adapters.embedding.exceptions import EmbeddingError
from app.adapters.vector.memory import InMemoryVectorStore
from app.adapters.vector.types import ChunkFilter
from app.domains.assets.model import Asset
from app.domains.knowledge.repository import KnowledgeDocumentRepository
from app.domains.rag.indexing import embedding_input_hash
from app.domains.rag.indexing_service import EmbeddingIndexer
from app.domains.rag.types import ChunkContentQuality, ChunkSourceType
from tests.knowledge.test_repository import data
from tests.rag.test_indexing_service import CountingEmbedder, create_event


def test_knowledge_fields_unchanged_and_replacement(db: Session) -> None:
    asset = Asset(symbol="A", name="A", market="NASDAQ")
    db.add(asset)
    db.flush()
    repo = KnowledgeDocumentRepository(db)
    document = repo.add(
        data(
            asset_id=asset.id,
            effective_date=date(2026, 10, 13),
            content="본문\n" * 1200,
        )
    )
    unlinked = repo.add(data("unlinked"))
    db.commit()
    store = InMemoryVectorStore()
    embedder = CountingEmbedder()
    indexer = EmbeddingIndexer(db, embedder, store)
    first = indexer.run(scan_page_size=1)
    assert (
        first.scanned,
        first.embedded_documents,
        first.chunks_written,
        first.unchanged,
        first.has_more,
    ) == (2, 2, 4, 0, False)
    records = [record for _, record in store._records.values()]
    linked = [record for record in records if record.source_id == document.id]
    assert len(linked) == 3
    assert all(record.source_type == ChunkSourceType.KNOWLEDGE for record in records)
    assert all(record.content_quality == ChunkContentQuality.FULL for record in records)
    assert all(record.asset_ids == [asset.id] for record in linked)
    assert linked[0].content.startswith(document.title + "\n\n" + "본문\n")
    assert linked[0].published_at is not None
    assert linked[0].published_at.isoformat() == "2026-10-13T00:00:00+09:00"
    assert linked[0].published_at.utcoffset() == timedelta(hours=9)
    other = next(record for record in records if record.source_id == unlinked.id)
    assert other.asset_ids == [] and other.published_at == unlinked.created_at
    assert linked[0].content_hash == embedding_input_hash(
        document.title + "\n\n" + document.content
    )
    assert linked[0].content_hash != document.content_hash
    again = indexer.run(scan_page_size=1)
    assert (
        again.scanned,
        again.embedded_documents,
        again.unchanged,
        again.has_more,
    ) == (2, 0, 2, False)
    assert len(embedder.calls) == 1
    document.content = "수정 본문"
    db.commit()
    result = indexer.run()
    assert (result.embedded_documents, result.unchanged, result.chunks_written) == (
        1,
        1,
        1,
    )
    assert len(store._records) == 2
    document.title = "수정 제목"
    db.commit()
    assert indexer.run().embedded_documents == 1
    assert len(store._records) == 2


def test_mixed_sources_share_limit_and_keep_same_id_separate(db: Session) -> None:
    news = create_event(db, 1)
    repo = KnowledgeDocumentRepository(db)
    docs = [repo.add(data(str(i))) for i in range(3)]
    db.commit()
    assert news.id == docs[0].id
    store = InMemoryVectorStore()
    embedder = CountingEmbedder()
    indexer = EmbeddingIndexer(db, embedder, store)
    first = indexer.run(max_documents=2, scan_page_size=2)
    assert (first.scanned, first.embedded_documents, first.has_more) == (2, 2, True)
    assert embedder.calls[0] == [news.title, docs[0].title + "\n\n" + docs[0].content]
    assert len(store._records) == 2
    second = indexer.run(max_documents=1, scan_page_size=1)
    assert (
        second.scanned,
        second.unchanged,
        second.embedded_documents,
        second.has_more,
    ) == (3, 2, 1, True)
    third = indexer.run(max_documents=2, scan_page_size=1)
    assert (
        third.scanned,
        third.unchanged,
        third.embedded_documents,
        third.has_more,
    ) == (4, 3, 1, False)
    query = embedder.embed(["보고서"])[0]
    news_hits = store.search(
        query,
        ChunkFilter(embedder.model_name, source_types=(ChunkSourceType.NEWS,)),
        10,
    )
    assert len(news_hits) == 1 and news_hits[0].source_id == news.id
    docs[0].content = "변경된 지식"
    db.commit()
    assert indexer.run().embedded_documents == 1
    assert (
        store.search(
            query,
            ChunkFilter(embedder.model_name, source_types=(ChunkSourceType.NEWS,)),
            10,
        )
        == news_hits
    )


def test_news_consumes_entire_limit_before_knowledge(db: Session) -> None:
    create_event(db, 1)
    KnowledgeDocumentRepository(db).add(data())
    db.commit()
    store = InMemoryVectorStore()
    indexer = EmbeddingIndexer(db, CountingEmbedder(), store)
    first = indexer.run(max_documents=1)
    assert (first.scanned, first.embedded_documents, first.has_more) == (1, 1, True)
    assert all(
        record.source_type == ChunkSourceType.NEWS
        for _, record in store._records.values()
    )
    second = indexer.run(max_documents=1)
    assert (
        second.scanned,
        second.unchanged,
        second.embedded_documents,
        second.has_more,
    ) == (2, 1, 1, True)
    assert not indexer.run(max_documents=1).has_more


@pytest.mark.parametrize("bad_vectors", [[], [[0.0]]])
def test_mixed_shape_failure_preserves_all_chunks(
    db: Session, bad_vectors: list[list[float]]
) -> None:
    news = create_event(db, 1)
    doc = KnowledgeDocumentRepository(db).add(data())
    db.commit()
    store = InMemoryVectorStore()
    embedder = CountingEmbedder()
    indexer = EmbeddingIndexer(db, embedder, store)
    indexer.run()
    original = dict(store._records)
    news.title = "변경 뉴스"
    doc.content = "변경 지식"
    db.commit()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(embedder, "embed", Mock(return_value=bad_vectors))
        commit = Mock(wraps=db.commit)
        patch.setattr(db, "commit", commit)
        with pytest.raises(EmbeddingError, match="shape mismatch"):
            indexer.run()
        commit.assert_not_called()
    assert store._records == original
    assert indexer.run().embedded_documents == 2
