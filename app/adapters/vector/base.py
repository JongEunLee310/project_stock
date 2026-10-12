from abc import ABC, abstractmethod

from app.adapters.vector.types import ChunkFilter, ChunkHit, ChunkRecord
from app.domains.rag.types import ChunkSourceType


class VectorStore(ABC):
    @abstractmethod
    def upsert(self, records: list[ChunkRecord]) -> int:
        raise NotImplementedError

    @abstractmethod
    def delete_by_source(self, source_type: ChunkSourceType, source_id: int) -> int:
        raise NotImplementedError

    @abstractmethod
    def get_content_hashes(
        self, source_type: ChunkSourceType, source_ids: list[int], embedding_model: str
    ) -> dict[int, str]:
        raise NotImplementedError

    @abstractmethod
    def search(
        self, query_vector: list[float], filters: ChunkFilter, k: int
    ) -> list[ChunkHit]:
        raise NotImplementedError
