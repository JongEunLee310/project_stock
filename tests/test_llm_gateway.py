import json
from decimal import Decimal
from typing import Any, ClassVar, cast

import pytest
from pydantic import BaseModel

from app.adapters.factory import get_llm_gateway
from app.adapters.llm.base import LLMClient, LLMMessage
from app.adapters.llm.exceptions import CloudBoundaryViolationError
from app.adapters.llm.gateway import CLOUD, LOCAL, LLMGateway
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
        return self.response


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

    assert result == {"summary": "ok"}
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

    assert result == {"summary": "local"}
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

    assert result == {"summary": "ok"}


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

    assert result == {"summary": "mocked"}


def test_get_llm_gateway_maps_mock_client_to_both_slots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")

    gateway = get_llm_gateway()

    assert isinstance(gateway.clients[CLOUD], MockLLMClient)
    assert gateway.clients[CLOUD] is gateway.clients[LOCAL]
