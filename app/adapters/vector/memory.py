import math
from copy import deepcopy
from datetime import UTC, datetime

from app.adapters.vector.base import VectorStore
from app.adapters.vector.types import ChunkFilter, ChunkHit, ChunkRecord
from app.domains.rag.types import ChunkSourceType


class InMemoryVectorStore(VectorStore):
    def __init__(self) -> None:
        self._records: dict[
            tuple[ChunkSourceType, int, int, str], tuple[int, ChunkRecord]
        ] = {}
        self._next_id = 1

    def upsert(self, records: list[ChunkRecord]) -> int:
        for record in records:
            key = (
                record.source_type,
                record.source_id,
                record.chunk_index,
                record.embedding_model,
            )
            existing = self._records.get(key)
            chunk_id = existing[0] if existing is not None else self._next_id
            if existing is None:
                self._next_id += 1
            self._records[key] = (chunk_id, deepcopy(record))
        return len(records)

    def delete_by_source(self, source_type: ChunkSourceType, source_id: int) -> int:
        keys = [key for key in self._records if key[:2] == (source_type, source_id)]
        for key in keys:
            del self._records[key]
        return len(keys)

    def get_content_hashes(
        self, source_type: ChunkSourceType, source_ids: list[int], embedding_model: str
    ) -> dict[int, str]:
        wanted = set(source_ids)
        return {
            record.source_id: record.content_hash
            for _, record in self._records.values()
            if record.source_type == source_type
            and record.source_id in wanted
            and record.embedding_model == embedding_model
        }

    def search(
        self, query_vector: list[float], filters: ChunkFilter, k: int
    ) -> list[ChunkHit]:
        if k <= 0:
            return []
        hits = []
        for chunk_id, record in self._records.values():
            if record.embedding_model != filters.embedding_model:
                continue
            if (
                filters.asset_id is not None
                and filters.asset_id not in record.asset_ids
            ):
                continue
            if filters.source_types and record.source_type not in filters.source_types:
                continue
            if filters.published_after is not None and (
                record.published_at is None
                or _as_utc(record.published_at) <= _as_utc(filters.published_after)
            ):
                continue
            if filters.published_before is not None and (
                record.published_at is None
                or _as_utc(record.published_at) >= _as_utc(filters.published_before)
            ):
                continue
            dot = sum(
                a * b for a, b in zip(query_vector, record.embedding, strict=True)
            )
            norm = math.sqrt(sum(a * a for a in query_vector)) * math.sqrt(
                sum(b * b for b in record.embedding)
            )
            score = dot / norm if norm else float("nan")
            hits.append(
                ChunkHit(
                    chunk_id=chunk_id,
                    source_type=record.source_type,
                    source_id=record.source_id,
                    chunk_index=record.chunk_index,
                    content=record.content,
                    content_quality=record.content_quality,
                    published_at=record.published_at,
                    score=score,
                )
            )
        return sorted(
            hits,
            key=lambda hit: (
                math.isnan(hit.score),
                -hit.score if not math.isnan(hit.score) else 0,
                hit.chunk_id,
            ),
        )[:k]


def _as_utc(value: datetime) -> datetime:
    # SQLite drops timezone information from UTC timestamps.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
