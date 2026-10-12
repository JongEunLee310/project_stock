from datetime import UTC, datetime

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.rag.model import DocumentChunk
from app.domains.rag.types import ChunkContentQuality, ChunkSourceType


def make_chunk(
    *,
    source_id: int = 439,
    chunk_index: int = 0,
    embedding_model: str = "test-embedding",
    quality: ChunkContentQuality = ChunkContentQuality.FULL,
    embedding: list[float] | None = None,
    asset_ids: list[int] | None = None,
) -> DocumentChunk:
    chunk = DocumentChunk(
        source_type=ChunkSourceType.NEWS.value,
        source_id=source_id,
        chunk_index=chunk_index,
        content="테스트 뉴스 청크",
        content_quality=quality.value,
        embedding=embedding if embedding is not None else [1.0] + [0.0] * 1535,
        embedding_model=embedding_model,
        published_at=datetime(2026, 10, 12, tzinfo=UTC),
        content_hash="a" * 64,
    )
    if asset_ids is not None:
        chunk.asset_ids = asset_ids
    return chunk


@pytest.mark.parametrize("quality", list(ChunkContentQuality))
@pytest.mark.parametrize("asset_ids", [[10, 20], [], None])
def test_sqlite_round_trip(
    db: Session, quality: ChunkContentQuality, asset_ids: list[int] | None
) -> None:
    chunk = make_chunk(quality=quality, asset_ids=asset_ids)
    db.add(chunk)
    db.commit()
    chunk_id = chunk.id
    db.expunge_all()

    loaded = db.get(DocumentChunk, chunk_id)
    assert loaded is not None
    assert loaded.embedding == [1.0] + [0.0] * 1535
    assert loaded.asset_ids == (asset_ids if asset_ids is not None else [])
    assert loaded.source_type == ChunkSourceType.NEWS.value
    assert loaded.content_quality == quality.value
    assert isinstance(loaded.source_type, str)
    assert isinstance(loaded.content_quality, str)
    assert loaded.content == "테스트 뉴스 청크"
    assert loaded.content_hash == "a" * 64
    assert loaded.created_at is not None


def test_sqlite_unique_source_chunk_model(db: Session) -> None:
    db.add(make_chunk())
    db.commit()
    db.add(make_chunk())
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()

    db.add_all(
        [
            make_chunk(source_id=440),
            make_chunk(chunk_index=1),
            make_chunk(embedding_model="other-embedding"),
        ]
    )
    db.commit()
    assert len(db.scalars(select(DocumentChunk)).all()) == 4


def test_sqlite_skips_postgres_indexes(db: Session) -> None:
    indexes = inspect(db.get_bind()).get_indexes("document_chunks")
    assert {index["name"] for index in indexes} == {
        "ix_document_chunks_published_at",
        "ix_document_chunks_source",
    }


@pytest.mark.postgres
def test_postgres_vector_round_trip(postgres_db: Session) -> None:
    assert postgres_db.scalar(
        text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
    )
    chunk = make_chunk(asset_ids=[10, 20])
    postgres_db.add(chunk)
    postgres_db.flush()
    chunk_id = chunk.id
    postgres_db.expunge_all()

    loaded = postgres_db.get(DocumentChunk, chunk_id)
    assert loaded is not None
    assert list(loaded.embedding) == [1.0] + [0.0] * 1535
    assert loaded.asset_ids == [10, 20]
    assert loaded.source_type == ChunkSourceType.NEWS.value
    assert loaded.content_quality == ChunkContentQuality.FULL.value
    assert loaded.published_at == datetime(2026, 10, 12, tzinfo=UTC)

    index_defs = dict(
        postgres_db.execute(
            text(
                "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'document_chunks'"
            )
        )
        .tuples()
        .all()
    )
    assert (
        "USING hnsw (embedding vector_cosine_ops)"
        in index_defs["ix_document_chunks_embedding"]
    )
    assert "USING gin (asset_ids)" in index_defs["ix_document_chunks_asset_ids"]


@pytest.mark.postgres
def test_postgres_cosine_distance_order(postgres_db: Session) -> None:
    vectors = [
        [1.0] + [0.0] * 1535,
        [0.0, 1.0] + [0.0] * 1534,
        [-1.0] + [0.0] * 1535,
    ]
    chunks = [make_chunk(chunk_index=i, embedding=v) for i, v in enumerate(vectors)]
    postgres_db.add_all(chunks)
    postgres_db.flush()
    ids = [chunk.id for chunk in chunks]
    distance = DocumentChunk.embedding.cosine_distance(vectors[0])
    rows = postgres_db.execute(
        select(DocumentChunk.id, distance)
        .where(DocumentChunk.id.in_(ids))
        .order_by(distance)
    ).all()
    assert [row[0] for row in rows] == ids
    assert [row[1] for row in rows] == pytest.approx([0.0, 1.0, 2.0])


@pytest.mark.postgres
def test_postgres_asset_ids_contains(postgres_db: Session) -> None:
    chunks = [
        make_chunk(chunk_index=0, asset_ids=[10, 20]),
        make_chunk(chunk_index=1, asset_ids=[20, 30]),
        make_chunk(chunk_index=2),
    ]
    postgres_db.add_all(chunks)
    postgres_db.flush()
    ids = [chunk.id for chunk in chunks]
    postgres_db.expunge_all()
    assert postgres_db.scalars(
        select(DocumentChunk.id).where(
            DocumentChunk.id.in_(ids), DocumentChunk.asset_ids.contains([10])
        )
    ).all() == [ids[0]]
    empty_chunk = postgres_db.get(DocumentChunk, ids[2])
    assert empty_chunk is not None
    assert empty_chunk.asset_ids == []
