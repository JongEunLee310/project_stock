from dataclasses import dataclass
from datetime import datetime

from app.domains.rag.types import ChunkContentQuality, ChunkSourceType


@dataclass(frozen=True)
class ChunkRecord:
    source_type: ChunkSourceType
    source_id: int
    chunk_index: int
    content: str
    content_quality: ChunkContentQuality
    embedding: list[float]
    embedding_model: str
    asset_ids: list[int]
    published_at: datetime | None
    content_hash: str


@dataclass(frozen=True)
class ChunkFilter:
    embedding_model: str
    asset_id: int | None = None
    source_types: tuple[ChunkSourceType, ...] = ()
    published_after: datetime | None = None


@dataclass(frozen=True)
class ChunkHit:
    chunk_id: int
    source_type: ChunkSourceType
    source_id: int
    chunk_index: int
    content: str
    content_quality: ChunkContentQuality
    published_at: datetime | None
    score: float
