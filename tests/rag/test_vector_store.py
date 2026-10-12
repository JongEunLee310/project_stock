from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.vector.base import VectorStore
from app.adapters.vector.memory import InMemoryVectorStore
from app.adapters.vector.pgvector import PgVectorStore
from app.adapters.vector.types import ChunkFilter, ChunkRecord
from app.domains.rag.model import DocumentChunk
from app.domains.rag.types import (
    EMBEDDING_DIMENSIONS,
    ChunkContentQuality,
    ChunkSourceType,
)

NOW = datetime(2026, 10, 12, tzinfo=UTC)


def vector(x: float, y: float = 0.0) -> list[float]:
    return [x, y] + [0.0] * (EMBEDDING_DIMENSIONS - 2)


def record(source_id: int, **changes: Any) -> ChunkRecord:
    return replace(
        ChunkRecord(
            source_type=ChunkSourceType.NEWS,
            source_id=source_id,
            chunk_index=0,
            content=f"news {source_id}",
            content_quality=ChunkContentQuality.FULL,
            embedding=vector(1.0),
            embedding_model="test-model-440",
            asset_ids=[10, 20],
            published_at=NOW,
            content_hash="a" * 64,
        ),
        **changes,
    )


@pytest.fixture(params=["memory", pytest.param("pgvector", marks=pytest.mark.postgres)])
def store(request: pytest.FixtureRequest) -> VectorStore:
    if request.param == "pgvector":
        db = request.getfixturevalue("postgres_db")
        # Keep the scenario independent of existing corpus data inside the rollback fixture.
        pg_store = PgVectorStore(db)
        for source_id in range(44001, 44010):
            pg_store.delete_by_source(ChunkSourceType.NEWS, source_id)
        return pg_store
    return InMemoryVectorStore()


def exercise_store(store: VectorStore) -> list[tuple[int, int, str, float]]:
    records = [
        record(44001),
        record(44002),
        record(44003, embedding=vector(0, 1)),
        record(44004, embedding=vector(-1)),
        record(44005, asset_ids=[30]),
        record(44006, published_at=NOW - timedelta(days=2)),
        record(44007, published_at=None),
        record(44008, embedding_model="other-model-440"),
        record(44001, embedding_model="other-model-440"),
    ]
    assert store.upsert([]) == 0
    assert store.upsert(records) == len(records)
    filters = ChunkFilter("test-model-440")
    initial = store.search(vector(1), filters, 20)
    assert len(initial) == 7
    old_id = next(hit.chunk_id for hit in initial if hit.source_id == 44001)
    changed = replace(
        records[0],
        content="updated",
        content_quality=ChunkContentQuality.SUMMARY,
        content_hash="b" * 64,
    )
    assert store.upsert([changed, changed]) == 2
    hits = store.search(vector(1), filters, 20)
    assert len(hits) == 7
    assert hits[0].chunk_id == old_id
    assert hits[0].content == "updated"
    assert hits[0].content_quality == ChunkContentQuality.SUMMARY
    assert hits[0].score == pytest.approx(1.0)
    assert [hit.score for hit in hits] == sorted(
        [hit.score for hit in hits], reverse=True
    )
    assert [hit.chunk_id for hit in hits if hit.score == pytest.approx(1.0)] == sorted(
        hit.chunk_id for hit in hits if hit.score == pytest.approx(1.0)
    )
    assert [hit.source_id for hit in hits[-2:]] == [44003, 44004]
    assert [hit.score for hit in hits[-2:]] == pytest.approx([0.0, -1.0])
    assert store.search(vector(1), filters, 2) == hits[:2]
    assert store.search(vector(1), filters, 0) == []
    assert store.search(vector(1), filters, -1) == []
    assert store.search(vector(1), replace(filters, asset_id=999), 20) == []
    assert len(store.search(vector(1), replace(filters, asset_id=10), 20)) == 6
    assert (
        len(
            store.search(
                vector(1), replace(filters, source_types=(ChunkSourceType.NEWS,)), 20
            )
        )
        == 7
    )
    assert (
        len(
            store.search(
                vector(1), replace(filters, published_after=NOW - timedelta(days=1)), 20
            )
        )
        == 5
    )
    assert store.search(vector(1), replace(filters, published_after=NOW), 20) == []
    combined = replace(
        filters,
        asset_id=10,
        source_types=(ChunkSourceType.NEWS,),
        published_after=NOW - timedelta(days=1),
    )
    filtered = store.search(vector(1), combined, 20)
    assert [hit.source_id for hit in filtered] == [44001, 44002, 44003, 44004]
    assert len(store.search(vector(1), ChunkFilter("other-model-440"), 20)) == 2
    assert store.delete_by_source(ChunkSourceType.NEWS, 44001) == 2
    assert store.delete_by_source(ChunkSourceType.NEWS, 44001) == 0
    assert len(store.search(vector(1), filters, 20)) == 6
    assert len(store.search(vector(1), ChunkFilter("other-model-440"), 20)) == 1
    return [
        (hit.source_id, hit.chunk_index, hit.content, hit.score) for hit in filtered
    ]


def test_shared_store_scenario(store: VectorStore) -> None:
    actual = exercise_store(store)
    expected = exercise_store(InMemoryVectorStore())
    assert actual == expected


def test_memory_snapshots_and_instance_isolation() -> None:
    store = InMemoryVectorStore()
    item = record(44001)
    store.upsert([item])
    item.embedding[0] = -1.0
    item.asset_ids.clear()
    hits = store.search(vector(1), ChunkFilter(item.embedding_model, asset_id=10), 1)
    assert len(hits) == 1
    assert hits[0].score == pytest.approx(1.0)
    assert (
        InMemoryVectorStore().search(vector(1), ChunkFilter(item.embedding_model), 1)
        == []
    )


@pytest.mark.postgres
def test_pgvector_caller_owns_transaction(postgres_db: Session) -> None:
    store = PgVectorStore(postgres_db)
    item = record(44009)
    store.delete_by_source(item.source_type, item.source_id)
    postgres_db.commit()
    store.upsert([item])
    loaded = postgres_db.scalar(
        select(DocumentChunk).where(
            DocumentChunk.source_id == item.source_id,
            DocumentChunk.embedding_model == item.embedding_model,
        )
    )
    assert loaded is not None
    assert loaded.content_hash == item.content_hash
    assert list(loaded.embedding) == item.embedding
    store.upsert([replace(item, content="changed", asset_ids=[30])])
    assert (
        store.search(vector(1), ChunkFilter(item.embedding_model, asset_id=30), 10)[
            0
        ].content
        == "changed"
    )
    postgres_db.rollback()
    assert (
        postgres_db.scalar(
            select(DocumentChunk.id).where(
                DocumentChunk.source_id == item.source_id,
                DocumentChunk.embedding_model == item.embedding_model,
            )
        )
        is None
    )


def test_upsert_updates_all_fields_and_deletes_all_chunks(store: VectorStore) -> None:
    original = record(44001)
    assert store.upsert([original, replace(original, chunk_index=1)]) == 2
    filters = ChunkFilter(original.embedding_model)
    original_id = store.search(vector(1), filters, 1)[0].chunk_id
    updated = replace(
        original,
        content="changed content",
        content_quality=ChunkContentQuality.TITLE_ONLY,
        embedding=vector(-1),
        asset_ids=[30],
        published_at=NOW - timedelta(days=1),
        content_hash="c" * 64,
    )
    assert store.upsert([updated]) == 1
    hits = store.search(vector(1), replace(filters, asset_id=30), 10)
    assert len(hits) == 1
    assert hits[0].chunk_id == original_id
    assert hits[0].content == updated.content
    assert hits[0].content_quality == updated.content_quality
    assert hits[0].published_at == updated.published_at
    assert hits[0].score == pytest.approx(-1.0)
    assert store.delete_by_source(original.source_type, original.source_id) == 2
    assert store.search(vector(1), filters, 10) == []
