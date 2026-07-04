import json
from decimal import Decimal
from typing import Any, ClassVar, cast

import pytest
from pydantic import BaseModel

from app.adapters.factory import get_llm_gateway
from app.adapters.llm.base import LLMClient, LLMMessage
from app.adapters.llm.budget import DailyCallBudget
from app.adapters.llm.cache import CachedCompletion, LLMResponseCache
from app.adapters.llm.exceptions import CloudBoundaryViolationError
from app.adapters.llm.gateway import CLOUD, LOCAL, LLMCompletionResult, LLMGateway
from app.adapters.llm.local import LocalLLMProvider
from app.adapters.llm.mock import MockLLMClient
from app.adapters.llm.privacy import (
    CloudSafePayload,
    PortfolioConcentrationSnapshot,
    to_concentration_snapshot,
)
from app.adapters.llm.router import LLMRouter, TaskRoute
from app.adapters.llm.types import LLMTaskType, SensitivityLevel
from app.core.config import settings
from app.domains.portfolios.model import Portfolio, Position


class ExampleResponse(BaseModel):
    summary: str


class RawPayload(CloudSafePayload):
    sensitivity: ClassVar[SensitivityLevel] = SensitivityLevel.RAW

    value: str


class SemiPayload(CloudSafePayload):
    sensitivity: ClassVar[SensitivityLevel] = SensitivityLevel.SEMI

    value: str


class SpyLLMClient(LLMClient):
    def __init__(self, response: dict[str, Any] | None = None) -> None:
        self.response = {"summary": "ok"} if response is None else response
        self.calls: list[list[LLMMessage]] = []
        self.timeouts: list[float | None] = []

    @property
    def provider_name(self) -> str:
        return "spy"

    @property
    def model_name(self) -> str:
        return "spy-model"

    def complete(
        self, messages: list[LLMMessage], timeout: float | None = None
    ) -> str:
        return "unused"

    def complete_json(
        self,
        messages: list[LLMMessage],
        schema: type[BaseModel],
        timeout: float | None = None,
    ) -> dict[str, Any]:
        self.calls.append(messages)
        self.timeouts.append(timeout)
        return self.response


class SpyCallBudget:
    def __init__(self) -> None:
        self.calls = 0

    def consume(self) -> None:
        self.calls += 1


class SpyResponseCache:
    def __init__(self, cached: CachedCompletion | None = None) -> None:
        self.cached = cached
        self.build_calls: list[tuple[LLMTaskType, CloudSafePayload, str, str]] = []
        self.lookup_calls: list[str] = []
        self.store_calls: list[tuple[str, dict[str, Any], str, str]] = []

    def build_key(
        self,
        task_type: LLMTaskType,
        payload: CloudSafePayload,
        system_prompt: str,
        model_name: str,
        schema: type[BaseModel],
    ) -> str:
        self.build_calls.append((task_type, payload, system_prompt, model_name))
        return "cache-key"

    def lookup(self, key: str) -> CachedCompletion | None:
        self.lookup_calls.append(key)
        return self.cached

    def store(
        self,
        key: str,
        output: dict[str, Any],
        provider: str,
        model_name: str,
    ) -> None:
        self.store_calls.append((key, output, provider, model_name))


def make_portfolio() -> Portfolio:
    return Portfolio(
        user_id=7,
        name="Retirement",
        concentration_threshold=Decimal("0.40"),
        cash_balance=Decimal("1000.00"),
    )


def make_position(
    asset_id: int,
    quantity: Decimal,
    avg_buy_price: Decimal,
) -> Position:
    return Position(
        portfolio_id=1,
        asset_id=asset_id,
        quantity=quantity,
        avg_buy_price=avg_buy_price,
    )


def make_snapshot() -> PortfolioConcentrationSnapshot:
    return to_concentration_snapshot(
        make_portfolio(),
        [
            make_position(
                asset_id=101,
                quantity=Decimal("10"),
                avg_buy_price=Decimal("100"),
            ),
            make_position(
                asset_id=102,
                quantity=Decimal("5"),
                avg_buy_price=Decimal("400"),
            ),
        ],
    )


def test_gateway_rejects_original_portfolio_before_calling_cloud_transport() -> None:
    cloud_client = SpyLLMClient()
    gateway = LLMGateway({CLOUD: cloud_client})

    with pytest.raises(CloudBoundaryViolationError):
        gateway.complete_json(
            LLMTaskType.PORTFOLIO_BRIEFING,
            cast(CloudSafePayload, make_portfolio()),
            ExampleResponse,
            "brief portfolio",
        )

    assert cloud_client.calls == []


@pytest.mark.parametrize(
    "payload",
    [
        RawPayload(value="raw"),
        SemiPayload(value="semi"),
    ],
)
def test_gateway_rejects_blocked_cloudsafe_sensitivity_before_transport(
    payload: CloudSafePayload,
) -> None:
    cloud_client = SpyLLMClient()
    gateway = LLMGateway({CLOUD: cloud_client})

    with pytest.raises(CloudBoundaryViolationError):
        gateway.complete_json(
            LLMTaskType.PORTFOLIO_BRIEFING,
            payload,
            ExampleResponse,
            "brief portfolio",
        )

    assert cloud_client.calls == []


def test_gateway_sends_only_cloudsafe_payload_body_to_transport() -> None:
    cloud_client = SpyLLMClient()
    gateway = LLMGateway({CLOUD: cloud_client})
    snapshot = make_snapshot()

    result = gateway.complete_json(
        LLMTaskType.PORTFOLIO_BRIEFING,
        snapshot,
        ExampleResponse,
        "brief portfolio",
    )

    assert result.output == {"summary": "ok"}
    assert result.provider == "spy"
    assert result.model_name == "spy-model"
    assert len(cloud_client.calls) == 1
    messages = cloud_client.calls[0]
    assert messages[0] == LLMMessage(role="system", content="brief portfolio")
    payload_body = json.loads(messages[1].content)
    assert payload_body == snapshot.as_payload()
    assert payload_body == {
        "position_count_band": "1-5",
        "largest_position_band": "40%+",
        "cash_band": "25-40%",
        "is_concentrated": True,
    }
    serialized_body = messages[1].content
    for forbidden in [
        "user_id",
        "cash_balance",
        "quantity",
        "avg_buy_price",
        "asset_id",
        "101",
        "102",
    ]:
        assert forbidden not in serialized_body


def test_gateway_selects_provider_through_router() -> None:
    cloud_client = SpyLLMClient({"summary": "cloud"})
    local_client = SpyLLMClient({"summary": "local"})
    router = LLMRouter(
        {
            LLMTaskType.PORTFOLIO_BRIEFING: TaskRoute(
                launch=LOCAL,
                future_primary=CLOUD,
            )
        }
    )
    gateway = LLMGateway(
        {CLOUD: cloud_client, LOCAL: local_client},
        router=router,
    )

    result = gateway.complete_json(
        LLMTaskType.PORTFOLIO_BRIEFING,
        make_snapshot(),
        ExampleResponse,
        "brief portfolio",
    )

    assert result.output == {"summary": "local"}
    assert result.provider == "spy"
    assert result.model_name == "spy-model"
    assert cloud_client.calls == []
    assert len(local_client.calls) == 1


@pytest.mark.parametrize("task_type", list(LLMTaskType))
def test_default_routes_do_not_call_local_provider(task_type: LLMTaskType) -> None:
    gateway = LLMGateway(
        {
            CLOUD: SpyLLMClient(),
            LOCAL: LocalLLMProvider(),
        }
    )

    result = gateway.complete_json(
        task_type,
        make_snapshot(),
        ExampleResponse,
        "brief portfolio",
    )

    assert result.output == {"summary": "ok"}


def test_gateway_runs_with_mock_client_in_cloud_slot() -> None:
    gateway = LLMGateway(
        {CLOUD: MockLLMClient({"ExampleResponse": {"summary": "mocked"}})}
    )

    result = gateway.complete_json(
        LLMTaskType.PORTFOLIO_BRIEFING,
        make_snapshot(),
        ExampleResponse,
        "brief portfolio",
    )

    assert result == LLMCompletionResult(
        output={"summary": "mocked"},
        provider="mock",
        model_name="mock",
    )


def test_gateway_passes_configured_timeout_to_client() -> None:
    cloud_client = SpyLLMClient()
    gateway = LLMGateway({CLOUD: cloud_client}, timeout_seconds=12.5)

    result = gateway.complete_json(
        LLMTaskType.PORTFOLIO_BRIEFING,
        make_snapshot(),
        ExampleResponse,
        "brief portfolio",
    )

    assert result.output == {"summary": "ok"}
    assert cloud_client.timeouts == [12.5]


def test_gateway_consumes_budget_for_cloud_route() -> None:
    budget = SpyCallBudget()
    gateway = LLMGateway(
        {CLOUD: SpyLLMClient()},
        call_budget=cast(DailyCallBudget, budget),
    )

    gateway.complete_json(
        LLMTaskType.PORTFOLIO_BRIEFING,
        make_snapshot(),
        ExampleResponse,
        "brief portfolio",
    )

    assert budget.calls == 1


def test_gateway_returns_cloud_cache_hit_without_client_or_budget_call() -> None:
    budget = SpyCallBudget()
    cloud_client = SpyLLMClient()
    cache = SpyResponseCache(
        CachedCompletion(
            output={"summary": "cached"},
            provider="openai",
            model_name="gpt-cached",
        )
    )
    gateway = LLMGateway(
        {CLOUD: cloud_client},
        call_budget=cast(DailyCallBudget, budget),
        response_cache=cast(LLMResponseCache, cache),
    )

    result = gateway.complete_json(
        LLMTaskType.PORTFOLIO_BRIEFING,
        make_snapshot(),
        ExampleResponse,
        "brief portfolio",
    )

    assert result == LLMCompletionResult(
        output={"summary": "cached"},
        provider="openai",
        model_name="gpt-cached",
        cached=True,
    )
    assert cloud_client.calls == []
    assert budget.calls == 0
    assert cache.lookup_calls == ["cache-key"]
    assert cache.store_calls == []


def test_gateway_stores_cloud_cache_miss_after_client_call() -> None:
    cache = SpyResponseCache()
    cloud_client = SpyLLMClient({"summary": "live"})
    gateway = LLMGateway(
        {CLOUD: cloud_client},
        response_cache=cast(LLMResponseCache, cache),
    )

    result = gateway.complete_json(
        LLMTaskType.PORTFOLIO_BRIEFING,
        make_snapshot(),
        ExampleResponse,
        "brief portfolio",
    )

    assert result.cached is False
    assert result.output == {"summary": "live"}
    assert len(cloud_client.calls) == 1
    assert cache.lookup_calls == ["cache-key"]
    assert cache.store_calls == [
        ("cache-key", {"summary": "live"}, "spy", "spy-model")
    ]


def test_gateway_does_not_lookup_cache_for_local_route() -> None:
    cache = SpyResponseCache(
        CachedCompletion(
            output={"summary": "cached"},
            provider="openai",
            model_name="gpt-cached",
        )
    )
    local_client = SpyLLMClient({"summary": "local"})
    router = LLMRouter(
        {
            LLMTaskType.PORTFOLIO_BRIEFING: TaskRoute(
                launch=LOCAL,
                future_primary=CLOUD,
            )
        }
    )
    gateway = LLMGateway(
        {CLOUD: SpyLLMClient(), LOCAL: local_client},
        router=router,
        response_cache=cast(LLMResponseCache, cache),
    )

    result = gateway.complete_json(
        LLMTaskType.PORTFOLIO_BRIEFING,
        make_snapshot(),
        ExampleResponse,
        "brief portfolio",
    )

    assert result.output == {"summary": "local"}
    assert result.cached is False
    assert cache.build_calls == []
    assert cache.lookup_calls == []
    assert len(local_client.calls) == 1


class RaisingRedisCache:
    def get(self, name: str) -> str | bytes | None:
        raise RuntimeError("redis get failed")

    def set(self, name: str, value: str, ex: int) -> object:
        raise RuntimeError("redis set failed")


def test_gateway_falls_back_to_live_cloud_call_when_cache_redis_errors() -> None:
    cloud_client = SpyLLMClient({"summary": "live"})
    cache = LLMResponseCache(RaisingRedisCache(), ttl_seconds=300)
    gateway = LLMGateway({CLOUD: cloud_client}, response_cache=cache)

    result = gateway.complete_json(
        LLMTaskType.PORTFOLIO_BRIEFING,
        make_snapshot(),
        ExampleResponse,
        "brief portfolio",
    )

    assert result == LLMCompletionResult(
        output={"summary": "live"},
        provider="spy",
        model_name="spy-model",
    )
    assert len(cloud_client.calls) == 1


def test_gateway_does_not_consume_budget_for_local_route() -> None:
    budget = SpyCallBudget()
    router = LLMRouter(
        {
            LLMTaskType.PORTFOLIO_BRIEFING: TaskRoute(
                launch=LOCAL,
                future_primary=CLOUD,
            )
        }
    )
    gateway = LLMGateway(
        {CLOUD: SpyLLMClient(), LOCAL: SpyLLMClient()},
        router=router,
        call_budget=cast(DailyCallBudget, budget),
    )

    gateway.complete_json(
        LLMTaskType.PORTFOLIO_BRIEFING,
        make_snapshot(),
        ExampleResponse,
        "brief portfolio",
    )

    assert budget.calls == 0


def test_get_llm_gateway_maps_mock_client_to_both_slots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")

    gateway = get_llm_gateway()

    assert isinstance(gateway.clients[CLOUD], MockLLMClient)
    assert gateway.clients[CLOUD] is gateway.clients[LOCAL]
