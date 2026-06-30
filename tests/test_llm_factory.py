from unittest.mock import Mock, patch

import pytest

from app.adapters.factory import get_llm_client
from app.adapters.llm.base import LLMMessage
from app.adapters.llm.local import LocalLLMProvider
from app.adapters.llm.mock import MockLLMClient
from app.adapters.llm.openai import OpenAIClient
from app.core.config import settings
from app.domains.news.schema import NewsSummaryResult
from app.domains.theses.conflict_schema import ThesisConflictResult


def test_get_llm_client_returns_seeded_mock_client() -> None:
    client = get_llm_client("mock")

    assert isinstance(client, MockLLMClient)
    assert client.complete_json(
        [LLMMessage(role="user", content="summarize")],
        NewsSummaryResult,
    ) == {
        "summary": "Mock analysis summary.",
        "positive_factors": ["Mock positive factor"],
        "negative_factors": ["Mock negative factor"],
        "impact_level": "HIGH",
        "sentiment": "NEUTRAL",
    }
    assert client.complete_json(
        [LLMMessage(role="user", content="check conflict")],
        ThesisConflictResult,
    ) == {
        "status": "NEUTRAL",
        "reason": "Mock conflict analysis is neutral.",
        "invalidation_triggered": False,
    }


def test_get_llm_client_returns_local_provider() -> None:
    assert isinstance(get_llm_client("local"), LocalLLMProvider)


def test_get_llm_client_returns_cloud_client_when_api_key_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-openai-key")

    with patch("app.adapters.llm.openai.openai.OpenAI", return_value=Mock()):
        client = get_llm_client("cloud")

    assert isinstance(client, OpenAIClient)


@pytest.mark.parametrize("api_key", [None, "", "   "])
def test_get_llm_client_fails_for_cloud_without_api_key(
    monkeypatch: pytest.MonkeyPatch,
    api_key: str | None,
) -> None:
    monkeypatch.setattr(settings, "OPENAI_API_KEY", api_key)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is required"):
        get_llm_client("cloud")


def test_get_llm_client_fails_for_unknown_provider() -> None:
    with pytest.raises(NotImplementedError, match="llm provider 미구현"):
        get_llm_client("unknown")


def test_get_llm_client_uses_settings_provider_when_provider_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")

    assert isinstance(get_llm_client(), MockLLMClient)
