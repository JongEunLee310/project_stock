from unittest.mock import Mock, patch

import pytest

import app.adapters.factory as factory
from app.adapters.factory import get_llm_client, get_llm_gateway
from app.adapters.llm.budget import DailyCallBudget
from app.adapters.llm.base import LLMMessage
from app.adapters.llm.cache import LLMResponseCache
from app.adapters.llm.escalation import EscalationPolicy
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
        "category": "OTHER",
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
    monkeypatch.setattr(settings, "OPENAI_BASE_URL", None)
    monkeypatch.setattr(settings, "OPENAI_MODEL", "gpt-test-model")

    with patch("app.adapters.llm.openai.openai.OpenAI", return_value=Mock()) as openai:
        client = get_llm_client("cloud")

    assert isinstance(client, OpenAIClient)
    assert client.model == "gpt-test-model"
    openai.assert_called_once_with(api_key="test-openai-key", base_url=None)


def test_get_llm_client_returns_cloud_client_with_base_url_without_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
    monkeypatch.setattr(settings, "OPENAI_BASE_URL", "http://127.0.0.1:10531/v1")
    monkeypatch.setattr(settings, "OPENAI_MODEL", "gpt-test-model")

    with patch("app.adapters.llm.openai.openai.OpenAI", return_value=Mock()) as openai:
        client = get_llm_client("cloud")

    assert isinstance(client, OpenAIClient)
    assert client.model == "gpt-test-model"
    openai.assert_called_once_with(
        api_key=factory.LOCAL_PROXY_OPENAI_API_KEY,
        base_url="http://127.0.0.1:10531/v1",
    )


def test_get_llm_client_returns_cloud_client_with_base_url_and_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setattr(settings, "OPENAI_BASE_URL", "http://127.0.0.1:10531/v1")
    monkeypatch.setattr(settings, "OPENAI_MODEL", "gpt-test-model")

    with patch("app.adapters.llm.openai.openai.OpenAI", return_value=Mock()) as openai:
        client = get_llm_client("cloud")

    assert isinstance(client, OpenAIClient)
    assert client.model == "gpt-test-model"
    openai.assert_called_once_with(
        api_key="test-openai-key",
        base_url="http://127.0.0.1:10531/v1",
    )


@pytest.mark.parametrize("api_key", [None, "", "   "])
def test_get_llm_client_fails_for_cloud_without_api_key(
    monkeypatch: pytest.MonkeyPatch,
    api_key: str | None,
) -> None:
    monkeypatch.setattr(settings, "OPENAI_API_KEY", api_key)
    monkeypatch.setattr(settings, "OPENAI_BASE_URL", None)

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

    def get(self, name: str) -> str | bytes | None:
        return None

    def set(self, name: str, value: str, ex: int) -> bool:
        return True


def test_get_llm_gateway_attaches_budget_for_cloud_with_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeRedis()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "cloud")
    monkeypatch.setattr(settings, "LLM_DAILY_CALL_LIMIT", 7)
    monkeypatch.setattr(settings, "LLM_CACHE_TTL_SECONDS", None)
    monkeypatch.setattr(settings, "LLM_ESCALATION_ENABLED", False)
    monkeypatch.setattr(settings, "LLM_ESCALATION_CONFIDENCE_THRESHOLD", None)
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
    monkeypatch.setattr(settings, "LLM_CACHE_TTL_SECONDS", None)
    monkeypatch.setattr(settings, "LLM_ESCALATION_ENABLED", False)
    monkeypatch.setattr(settings, "LLM_ESCALATION_CONFIDENCE_THRESHOLD", None)
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
    assert gateway.response_cache is None


def test_get_llm_gateway_attaches_cache_for_cloud_with_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeRedis()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "cloud")
    monkeypatch.setattr(settings, "LLM_DAILY_CALL_LIMIT", None)
    monkeypatch.setattr(settings, "LLM_CACHE_TTL_SECONDS", 600)
    monkeypatch.setattr(settings, "LLM_ESCALATION_ENABLED", False)
    monkeypatch.setattr(settings, "LLM_ESCALATION_CONFIDENCE_THRESHOLD", None)
    monkeypatch.setattr(factory, "get_redis_connection", lambda: redis)
    monkeypatch.setattr(
        factory,
        "get_llm_client",
        lambda provider: MockLLMClient({"default": {"summary": provider}}),
    )

    gateway = get_llm_gateway()

    assert gateway.call_budget is None
    assert isinstance(gateway.response_cache, LLMResponseCache)
    assert gateway.response_cache.redis is redis
    assert gateway.response_cache.ttl_seconds == 600


def test_get_llm_gateway_skips_cache_for_cloud_without_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", "cloud")
    monkeypatch.setattr(settings, "LLM_DAILY_CALL_LIMIT", None)
    monkeypatch.setattr(settings, "LLM_CACHE_TTL_SECONDS", None)
    monkeypatch.setattr(settings, "LLM_ESCALATION_ENABLED", False)
    monkeypatch.setattr(settings, "LLM_ESCALATION_CONFIDENCE_THRESHOLD", None)
    monkeypatch.setattr(
        factory,
        "get_redis_connection",
        lambda: pytest.fail("redis should not be created without cache or budget"),
    )
    monkeypatch.setattr(
        factory,
        "get_llm_client",
        lambda provider: MockLLMClient({"default": {"summary": provider}}),
    )

    gateway = get_llm_gateway()

    assert gateway.call_budget is None
    assert gateway.response_cache is None


@pytest.mark.parametrize("provider", ["mock", "local"])
def test_get_llm_gateway_skips_budget_for_non_cloud_providers(
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", provider)
    monkeypatch.setattr(settings, "LLM_DAILY_CALL_LIMIT", 7)
    monkeypatch.setattr(settings, "LLM_CACHE_TTL_SECONDS", 600)
    monkeypatch.setattr(settings, "LLM_ESCALATION_ENABLED", True)
    monkeypatch.setattr(settings, "LLM_ESCALATION_CONFIDENCE_THRESHOLD", 0.8)
    monkeypatch.setattr(
        factory,
        "get_redis_connection",
        lambda: pytest.fail("redis should not be created for non-cloud providers"),
    )

    gateway = get_llm_gateway()

    assert gateway.call_budget is None
    assert gateway.response_cache is None
    assert gateway.escalation_policy is None
    if provider == "mock":
        assert isinstance(gateway.clients[CLOUD], MockLLMClient)
        assert gateway.clients[CLOUD] is gateway.clients[LOCAL]
    else:
        assert isinstance(gateway.clients[LOCAL], LocalLLMProvider)


def test_get_llm_gateway_attaches_escalation_policy_for_cloud_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", "cloud")
    monkeypatch.setattr(settings, "LLM_DAILY_CALL_LIMIT", None)
    monkeypatch.setattr(settings, "LLM_CACHE_TTL_SECONDS", None)
    monkeypatch.setattr(settings, "LLM_ESCALATION_ENABLED", True)
    monkeypatch.setattr(settings, "LLM_ESCALATION_CONFIDENCE_THRESHOLD", 0.8)
    monkeypatch.setattr(
        factory,
        "get_llm_client",
        lambda provider: MockLLMClient({"default": {"summary": provider}}),
    )

    gateway = get_llm_gateway()

    assert isinstance(gateway.escalation_policy, EscalationPolicy)
    assert gateway.escalation_policy.confidence_threshold == 0.8


def test_get_llm_gateway_skips_escalation_policy_by_default_for_cloud(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", "cloud")
    monkeypatch.setattr(settings, "LLM_DAILY_CALL_LIMIT", None)
    monkeypatch.setattr(settings, "LLM_CACHE_TTL_SECONDS", None)
    monkeypatch.setattr(settings, "LLM_ESCALATION_ENABLED", False)
    monkeypatch.setattr(settings, "LLM_ESCALATION_CONFIDENCE_THRESHOLD", 0.8)
    monkeypatch.setattr(
        factory,
        "get_llm_client",
        lambda provider: MockLLMClient({"default": {"summary": provider}}),
    )

    gateway = get_llm_gateway()

    assert gateway.escalation_policy is None
