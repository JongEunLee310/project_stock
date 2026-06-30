import pytest
from pydantic import BaseModel

from app.adapters.llm.base import LLMMessage
from app.adapters.llm.local import LocalLLMProvider


class ExampleResponse(BaseModel):
    summary: str


def test_local_llm_provider_complete_is_not_ready() -> None:
    provider = LocalLLMProvider()

    with pytest.raises(
        NotImplementedError,
        match="Local LLM provider is not ready yet.",
    ):
        provider.complete([LLMMessage(role="user", content="hello")])


def test_local_llm_provider_complete_json_is_not_ready() -> None:
    provider = LocalLLMProvider()

    with pytest.raises(
        NotImplementedError,
        match="Local LLM provider is not ready yet.",
    ):
        provider.complete_json(
            [LLMMessage(role="user", content="hello")],
            ExampleResponse,
        )
