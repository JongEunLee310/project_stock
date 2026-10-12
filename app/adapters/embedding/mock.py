import hashlib
import math
import random

from app.adapters.embedding.base import Embedder
from app.domains.rag.types import EMBEDDING_DIMENSIONS


class MockEmbedder(Embedder):
    def __init__(self, dimensions: int = EMBEDDING_DIMENSIONS) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self._dimensions = dimensions

    @property
    def model_name(self) -> str:
        return "mock-embedding"

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            seed = int.from_bytes(hashlib.sha256(text.encode()).digest(), "big")
            rng = random.Random(seed)
            vector = [rng.uniform(-1.0, 1.0) for _ in range(self.dimensions)]
            norm = math.sqrt(sum(value * value for value in vector))
            vectors.append([value / norm for value in vector])
        return vectors
