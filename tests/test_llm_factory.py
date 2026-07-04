from unittest.mock import Mock, patch

import pytest

import app.adapters.factory as factory
from app.adapters.factory import get_llm_client, get_llm_gateway
from app.adapters.llm.budget import DailyCallBudget
from app.adapters.llm.base import LLMMessage
from app.adapters.llm.gateway import CLOUD, LOCAL
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
    monkeypatch.setattr(settings, "OPENAI_MODEL", "gpt-test-model")

    with patch("app.adapters.llm.openai.openai.OpenAI", return_value=Mock()):
        client = get_llm_client("cloud")

    assert isinstance(client, OpenAIClient)
    assert client.model == "gpt-test-model"


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


class FakeRedis:
    def incr(self, name: str) -> int:
        return 1

    def expire(self, name: str, time: int) -> bool:
        return True


def test_get_llm_gateway_attaches_budget_for_cloud_with_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeRedis()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "cloud")
    monkeypatch.setattr(settings, "LLM_DAILY_CALL_LIMIT", 7)
    monkeypatch.setattr(settings, "LLM_TIMEOUT_SECONDS", 3)
    monkeypatch.setattr(factory, "get_redis_connection", lambda: redis)
    monkeypatch.setattr(
        factory,
        "get_llm_client",
        lambda provider: MockLLMClient({"default": {"summary": provider}}),
    )

    gateway = get_llm_gateway()

    assert isinstance(gateway.call_budget, DailyCallBudget)
    assert gateway.call_budget.redis is redis
    assert gateway.call_budget.limit == 7
    assert gateway.timeout_seconds == 3


def test_get_llm_gateway_skips_budget_for_cloud_without_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", "cloud")
    monkeypatch.setattr(settings, "LLM_DAILY_CALL_LIMIT", None)
    monkeypatch.setattr(
        factory,
        "get_redis_connection",
        lambda: pytest.fail("redis should not be created without a limit"),
    )
    monkeypatch.setattr(
        factory,
        "get_llm_client",
        lambda provider: MockLLMClient({"default": {"summary": provider}}),
    )

    gateway = get_llm_gateway()

    assert gateway.call_budget is None


@pytest.mark.parametrize("provider", ["mock", "local"])
def test_get_llm_gateway_skips_budget_for_non_cloud_providers(
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", provider)
    monkeypatch.setattr(settings, "LLM_DAILY_CALL_LIMIT", 7)
    monkeypatch.setattr(
        factory,
        "get_redis_connection",
        lambda: pytest.fail("redis should not be created for non-cloud providers"),
    )

    gateway = get_llm_gateway()

    assert gateway.call_budget is None
    if provider == "mock":
        assert isinstance(gateway.clients[CLOUD], MockLLMClient)
        assert gateway.clients[CLOUD] is gateway.clients[LOCAL]
    else:
        assert isinstance(gateway.clients[LOCAL], LocalLLMProvider)
