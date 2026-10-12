import math
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

import openai
import pytest
from sqlalchemy.orm import Session

from app.adapters.embedding.exceptions import EmbeddingDimensionError, EmbeddingError
from app.adapters.embedding.mock import MockEmbedder
from app.adapters.embedding.openai import OpenAIEmbedder
from app.adapters.factory import get_embedder, get_vector_store
from app.adapters.vector.memory import InMemoryVectorStore
from app.adapters.vector.pgvector import PgVectorStore
from app.core.config import Settings, settings
from app.domains.rag.types import EMBEDDING_DIMENSIONS


def test_mock_embedding() -> None:
    embedder = MockEmbedder(dimensions=12)
    vectors = embedder.embed(["same", "different", "same"])
    assert vectors[0] == vectors[2] == MockEmbedder(12).embed(["same"])[0]
    assert vectors[0] != vectors[1]
    assert all(len(vector) == embedder.dimensions == 12 for vector in vectors)
    assert [math.sqrt(sum(x * x for x in v)) for v in vectors] == pytest.approx([1] * 3)
    assert embedder.embed([]) == []
    assert MockEmbedder().dimensions == EMBEDDING_DIMENSIONS
    assert embedder.model_name == "mock-embedding"


@pytest.fixture
def fake_openai(monkeypatch: pytest.MonkeyPatch) -> Mock:
    client = Mock()
    monkeypatch.setattr(
        "app.adapters.embedding.openai.openai.OpenAI", Mock(return_value=client)
    )
    return client


def test_openai_batches_and_order(fake_openai: Mock) -> None:
    def create(**kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(
            data=[
                SimpleNamespace(index=index, embedding=[float(text), 1.0])
                for index, text in reversed(list(enumerate(kwargs["input"])))
            ]
        )

    fake_openai.embeddings.create.side_effect = create
    embedder = OpenAIEmbedder("test-key", model="test-model", dimensions=2)
    assert embedder.embed([]) == []
    fake_openai.embeddings.create.assert_not_called()
    vectors = embedder.embed([str(i) for i in range(205)])
    assert vectors == [[float(i), 1.0] for i in range(205)]
    assert [
        len(call.kwargs["input"])
        for call in fake_openai.embeddings.create.call_args_list
    ] == [100, 100, 5]
    assert all(
        call.kwargs["model"] == "test-model" and call.kwargs["dimensions"] == 2
        for call in fake_openai.embeddings.create.call_args_list
    )
    assert embedder.model_name == "test-model"


def test_openai_dimension_mismatch(fake_openai: Mock) -> None:
    fake_openai.embeddings.create.return_value = SimpleNamespace(
        data=[SimpleNamespace(index=0, embedding=[1.0])]
    )
    with pytest.raises(EmbeddingDimensionError):
        OpenAIEmbedder("key", dimensions=2).embed(["text"])


@pytest.mark.parametrize("indices", [[], [0, 0], [1]])
def test_openai_invalid_indices(fake_openai: Mock, indices: list[int]) -> None:
    fake_openai.embeddings.create.return_value = SimpleNamespace(
        data=[SimpleNamespace(index=i, embedding=[1.0, 0.0]) for i in indices]
    )
    with pytest.raises(EmbeddingError, match="indices"):
        OpenAIEmbedder("key", dimensions=2).embed(["text"])


def test_openai_error_boundary(fake_openai: Mock) -> None:
    error = openai.OpenAIError("failed")
    fake_openai.embeddings.create.side_effect = error
    with pytest.raises(EmbeddingError) as raised:
        OpenAIEmbedder("key").embed(["text"])
    assert raised.value.__cause__ is error


def test_mock_factories(db: Session) -> None:
    assert isinstance(get_embedder(), MockEmbedder)
    assert isinstance(get_vector_store(db), InMemoryVectorStore)
    assert get_vector_store(db) is not get_vector_store(db)


def test_pgvector_factory(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "VECTOR_STORE_PROVIDER", "pgvector")
    store = get_vector_store(db)
    assert isinstance(store, PgVectorStore)
    assert store.db is db


@pytest.mark.parametrize(
    "embedding_key,openai_key,expected_key",
    [
        ("embedding-key", "chat-key", "embedding-key"),
        (None, "chat-key", "chat-key"),
    ],
)
@pytest.mark.parametrize("base_url", [None, "https://embedding.example/v1"])
def test_openai_factory(
    monkeypatch: pytest.MonkeyPatch,
    fake_openai: Mock,
    embedding_key: str | None,
    openai_key: str | None,
    expected_key: str,
    base_url: str | None,
) -> None:
    constructor = Mock(return_value=fake_openai)
    monkeypatch.setattr("app.adapters.embedding.openai.openai.OpenAI", constructor)
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "openai")
    monkeypatch.setattr(settings, "EMBEDDING_API_KEY", embedding_key)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", openai_key)
    monkeypatch.setattr(settings, "OPENAI_BASE_URL", "https://chat-proxy.example/v1")
    monkeypatch.setattr(settings, "EMBEDDING_BASE_URL", base_url)
    monkeypatch.setattr(settings, "EMBEDDING_MODEL", "chosen-model")
    embedder = get_embedder()
    assert isinstance(embedder, OpenAIEmbedder)
    assert embedder.model_name == "chosen-model"
    assert embedder.dimensions == EMBEDDING_DIMENSIONS
    constructor.assert_called_once_with(
        api_key=expected_key, base_url=base_url or "https://api.openai.com/v1"
    )


def test_factory_missing_keys(
    monkeypatch: pytest.MonkeyPatch, fake_openai: Mock
) -> None:
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "openai")
    monkeypatch.setattr(settings, "EMBEDDING_API_KEY", None)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
    with pytest.raises(
        RuntimeError,
        match="EMBEDDING_API_KEY or OPENAI_API_KEY is required when EMBEDDING_PROVIDER=openai",
    ):
        get_embedder()
    fake_openai.embeddings.create.assert_not_called()


def test_embedding_settings() -> None:
    settings_cls = cast(Any, Settings)
    configured = cast(
        Settings,
        settings_cls(_env_file=None, EMBEDDING_BASE_URL="  ", EMBEDDING_API_KEY=""),
    )
    assert configured.EMBEDDING_BASE_URL is None
    assert configured.EMBEDDING_API_KEY is None
    assert configured.EMBEDDING_MODEL == "text-embedding-3-small"


def test_openai_does_not_inherit_environment_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://chat-proxy.example/v1")
    embedder = OpenAIEmbedder("test-key")
    try:
        assert str(embedder.client.base_url) == "https://api.openai.com/v1/"
    finally:
        embedder.client.close()
