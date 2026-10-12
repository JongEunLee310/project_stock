import openai

from app.adapters.embedding.base import Embedder
from app.adapters.embedding.exceptions import EmbeddingDimensionError, EmbeddingError
from app.domains.rag.types import EMBEDDING_DIMENSIONS


class OpenAIEmbedder(Embedder):
    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        base_url: str | None = None,
        dimensions: int = EMBEDDING_DIMENSIONS,
    ) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self._model = model
        self._dimensions = dimensions
        # The SDK otherwise inherits OPENAI_BASE_URL from the chat configuration.
        self.client = openai.OpenAI(
            api_key=api_key, base_url=base_url or "https://api.openai.com/v1"
        )

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), 100):
            batch = texts[start : start + 100]
            try:
                response = self.client.embeddings.create(
                    input=batch,
                    model=self.model_name,
                    dimensions=self.dimensions,
                    encoding_format="float",
                )
            except openai.OpenAIError as exc:
                raise EmbeddingError("OpenAI embedding request failed") from exc
            ordered = sorted(response.data, key=lambda item: item.index)
            if [item.index for item in ordered] != list(range(len(batch))):
                raise EmbeddingError("OpenAI returned invalid embedding indices")
            for item in ordered:
                if len(item.embedding) != self.dimensions:
                    raise EmbeddingDimensionError(
                        f"Expected {self.dimensions} dimensions, got {len(item.embedding)}"
                    )
                vectors.append(item.embedding)
        return vectors
