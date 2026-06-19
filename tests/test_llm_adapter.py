from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch

import pytest
from pydantic import BaseModel

from app.adapters.llm.base import LLMMessage
from app.adapters.llm.exceptions import LLMCallError, LLMTimeoutError
from app.adapters.llm.mock import MockLLMClient
from app.adapters.llm.openai import OpenAIClient


class ExampleResponse(BaseModel):
    summary: str


def _completion(content: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def test_mock_llm_client_complete_returns_default_response() -> None:
    client = MockLLMClient()

    result = client.complete([LLMMessage(role="user", content="hello")])

    assert result == "mock response"


def test_mock_llm_client_complete_json_returns_injected_response() -> None:
    client = MockLLMClient({"ExampleResponse": {"summary": "mocked"}})

    result = client.complete_json(
        [LLMMessage(role="user", content="summarize")],
        ExampleResponse,
    )

    assert result == {"summary": "mocked"}


def test_mock_llm_client_complete_json_wraps_non_dict_response() -> None:
    client = MockLLMClient({"ExampleResponse": "plain response"})

    result = client.complete_json(
        [LLMMessage(role="user", content="summarize")],
        ExampleResponse,
    )

    assert result == {"response": "plain response"}


def test_openai_client_complete_returns_response() -> None:
    openai_instance = Mock()
    openai_instance.chat.completions.create.return_value = _completion("hello")

    with patch("app.adapters.llm.openai.openai.OpenAI", return_value=openai_instance):
        client = OpenAIClient(api_key="test-key", model="test-model")
        result = client.complete(
            [LLMMessage(role="user", content="hello")],
            timeout=5,
        )

    assert result == "hello"
    openai_instance.chat.completions.create.assert_called_once_with(
        model="test-model",
        messages=[{"role": "user", "content": "hello"}],
        timeout=5,
    )


def test_openai_client_complete_converts_timeout_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DummyTimeoutError(Exception):
        pass

    openai_instance = Mock()
    openai_instance.chat.completions.create.side_effect = DummyTimeoutError("timeout")
    monkeypatch.setattr("app.adapters.llm.openai.openai.APITimeoutError", DummyTimeoutError)

    with patch("app.adapters.llm.openai.openai.OpenAI", return_value=openai_instance):
        client = OpenAIClient(api_key="test-key")

        with pytest.raises(LLMTimeoutError):
            client.complete([LLMMessage(role="user", content="hello")])


def test_openai_client_complete_converts_openai_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DummyOpenAIError(Exception):
        pass

    openai_instance = Mock()
    openai_instance.chat.completions.create.side_effect = DummyOpenAIError("failed")
    monkeypatch.setattr("app.adapters.llm.openai.openai.OpenAIError", DummyOpenAIError)

    with patch("app.adapters.llm.openai.openai.OpenAI", return_value=openai_instance):
        client = OpenAIClient(api_key="test-key")

        with pytest.raises(LLMCallError):
            client.complete([LLMMessage(role="user", content="hello")])


def test_openai_client_complete_json_parses_json_response() -> None:
    openai_instance = Mock()
    openai_instance.chat.completions.create.return_value = _completion(
        '{"summary": "parsed"}'
    )

    with patch("app.adapters.llm.openai.openai.OpenAI", return_value=openai_instance):
        client = OpenAIClient(api_key="test-key", model="test-model")
        result = client.complete_json(
            [LLMMessage(role="user", content="summarize")],
            ExampleResponse,
            timeout=10,
        )

    assert result == {"summary": "parsed"}
    call_kwargs: dict[str, Any] = openai_instance.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "test-model"
    assert call_kwargs["response_format"] == {"type": "json_object"}
    assert call_kwargs["timeout"] == 10
    assert "JSON Schema" in call_kwargs["messages"][0]["content"]


def test_openai_client_complete_json_converts_timeout_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DummyTimeoutError(Exception):
        pass

    openai_instance = Mock()
    openai_instance.chat.completions.create.side_effect = DummyTimeoutError("timeout")
    monkeypatch.setattr("app.adapters.llm.openai.openai.APITimeoutError", DummyTimeoutError)

    with patch("app.adapters.llm.openai.openai.OpenAI", return_value=openai_instance):
        client = OpenAIClient(api_key="test-key")

        with pytest.raises(LLMTimeoutError):
            client.complete_json(
                [LLMMessage(role="user", content="summarize")],
                ExampleResponse,
            )


def test_openai_client_complete_json_converts_openai_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DummyOpenAIError(Exception):
        pass

    openai_instance = Mock()
    openai_instance.chat.completions.create.side_effect = DummyOpenAIError("failed")
    monkeypatch.setattr("app.adapters.llm.openai.openai.OpenAIError", DummyOpenAIError)

    with patch("app.adapters.llm.openai.openai.OpenAI", return_value=openai_instance):
        client = OpenAIClient(api_key="test-key")

        with pytest.raises(LLMCallError):
            client.complete_json(
                [LLMMessage(role="user", content="summarize")],
                ExampleResponse,
            )


def test_openai_client_complete_json_rejects_invalid_json() -> None:
    openai_instance = Mock()
    openai_instance.chat.completions.create.return_value = _completion("not json")

    with patch("app.adapters.llm.openai.openai.OpenAI", return_value=openai_instance):
        client = OpenAIClient(api_key="test-key")

        with pytest.raises(LLMCallError, match="invalid JSON"):
            client.complete_json(
                [LLMMessage(role="user", content="summarize")],
                ExampleResponse,
            )


def test_openai_client_complete_json_rejects_non_object_json() -> None:
    openai_instance = Mock()
    openai_instance.chat.completions.create.return_value = _completion(
        '["not", "an", "object"]'
    )

    with patch("app.adapters.llm.openai.openai.OpenAI", return_value=openai_instance):
        client = OpenAIClient(api_key="test-key")

        with pytest.raises(LLMCallError, match="not an object"):
            client.complete_json(
                [LLMMessage(role="user", content="summarize")],
                ExampleResponse,
            )
