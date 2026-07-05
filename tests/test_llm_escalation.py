import json
from dataclasses import FrozenInstanceError
from typing import Any, ClassVar, cast

import pytest
from pydantic import BaseModel

from app.adapters.llm.base import LLMClient, LLMMessage
from app.adapters.llm.budget import DailyCallBudget
from app.adapters.llm.cache import LLMResponseCache
from app.adapters.llm.escalation import EscalationPolicy, EscalationSignal
from app.adapters.llm.exceptions import LLMBudgetExceededError
from app.adapters.llm.gateway import CLOUD, LOCAL, LLMGateway
from app.adapters.llm.privacy import CloudSafePayload
from app.adapters.llm.router import LLMRouter, TaskRoute
from app.adapters.llm.types import LLMTaskType, RiskLevel, SensitivityLevel


class ExampleResponse(BaseModel):
    summary: str


class ConfidenceResponse(BaseModel):
    summary: str
    confidence: float


class PublicPayload(CloudSafePayload):
    sensitivity: ClassVar[SensitivityLevel] = SensitivityLevel.PUBLIC

    value: str


class RawPayload(CloudSafePayload):
    sensitivity: ClassVar[SensitivityLevel] = SensitivityLevel.RAW

    value: str


class SpyLLMClient(LLMClient):
    def __init__(
        self,
        responses: list[dict[str, Any]] | None = None,
        *,
        provider_name: str = "spy",
        model_name: str = "spy-model",
        error: Exception | None = None,
    ) -> None:
        self.responses = [{"summary": "ok"}] if responses is None else responses
        self._provider_name = provider_name
        self._model_name = model_name
        self.error = error
        self.calls: list[list[LLMMessage]] = []

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def model_name(self) -> str:
        return self._model_name

    def complete(
        self,
        messages: list[LLMMessage],
        timeout: float | None = None,
    ) -> str:
        return "unused"

    def complete_json(
        self,
        messages: list[LLMMessage],
        schema: type[BaseModel],
        timeout: float | None = None,
    ) -> dict[str, Any]:
        self.calls.append(messages)
        if self.error is not None:
            raise self.error
        index = min(len(self.calls) - 1, len(self.responses) - 1)
        return self.responses[index]


class SpyCallBudget:
    def __init__(self) -> None:
        self.calls = 0

    def consume(self) -> None:
        self.calls += 1


class FailingCallBudget:
    def __init__(self) -> None:
        self.calls = 0

    def consume(self) -> None:
        self.calls += 1
        raise LLMBudgetExceededError("daily cloud LLM call limit exceeded")


class SpyResponseCache:
    def __init__(self) -> None:
        self.build_calls = 0
        self.lookup_calls = 0
        self.store_calls = 0

    def build_key(
        self,
        task_type: LLMTaskType,
        payload: CloudSafePayload,
        system_prompt: str,
        model_name: str,
        schema: type[BaseModel],
    ) -> str:
        self.build_calls += 1
        return "cache-key"

    def lookup(self, key: str) -> None:
        self.lookup_calls += 1
        return None

    def store(
        self,
        key: str,
        output: dict[str, Any],
        provider: str,
        model_name: str,
    ) -> None:
        self.store_calls += 1


def local_router() -> LLMRouter:
    return LLMRouter(
        {
            LLMTaskType.PORTFOLIO_BRIEFING: TaskRoute(
                launch=LOCAL,
                future_primary=CLOUD,
            )
        }
    )


def test_escalation_signal_defaults_and_frozen() -> None:
    signal = EscalationSignal()

    assert signal.risk_level == RiskLevel.LOW
    assert signal.loss_spike is False
    assert signal.news_sentiment_swing is False
    assert signal.event_flag is False
    assert signal.trade_question is False
    with pytest.raises(FrozenInstanceError):
        signal.loss_spike = True  # type: ignore[misc]


@pytest.mark.parametrize(
    "signal",
    [
        EscalationSignal(risk_level=RiskLevel.HIGH),
        EscalationSignal(loss_spike=True),
        EscalationSignal(news_sentiment_swing=True),
        EscalationSignal(event_flag=True),
        EscalationSignal(trade_question=True),
    ],
)
def test_policy_escalates_before_for_local_trigger_fields(
    signal: EscalationSignal,
) -> None:
    assert EscalationPolicy().should_escalate_before(signal, LOCAL) is True


def test_policy_does_not_escalate_before_without_trigger() -> None:
    policy = EscalationPolicy()

    assert policy.should_escalate_before(EscalationSignal(), LOCAL) is False
    assert (
        policy.should_escalate_before(
            EscalationSignal(risk_level=RiskLevel.MEDIUM),
            LOCAL,
        )
        is False
    )


def test_policy_does_not_escalate_before_when_provider_is_cloud() -> None:
    signal = EscalationSignal(
        risk_level=RiskLevel.HIGH,
        loss_spike=True,
        news_sentiment_swing=True,
        event_flag=True,
        trade_question=True,
    )

    assert EscalationPolicy().should_escalate_before(signal, CLOUD) is False


def test_policy_verifies_after_for_low_confidence() -> None:
    policy = EscalationPolicy(confidence_threshold=0.7)

    assert (
        policy.should_verify_after(
            {"summary": "ok", "confidence": 0.69},
            ConfidenceResponse,
            LOCAL,
        )
        is True
    )
    assert (
        policy.should_verify_after(
            {"summary": "ok", "confidence": 0.7},
            ConfidenceResponse,
            LOCAL,
        )
        is False
    )


def test_policy_verifies_after_for_schema_failure() -> None:
    assert (
        EscalationPolicy().should_verify_after(
            {"confidence": 0.9},
            ConfidenceResponse,
            LOCAL,
        )
        is True
    )


def test_policy_does_not_verify_after_for_cloud_first_provider() -> None:
    assert (
        EscalationPolicy(confidence_threshold=0.9).should_verify_after(
            {"confidence": 0.1},
            ConfidenceResponse,
            CLOUD,
        )
        is False
    )


def test_policy_ignores_confidence_when_threshold_is_none_or_value_missing() -> None:
    policy = EscalationPolicy(confidence_threshold=None)

    assert (
        policy.should_verify_after(
            {"summary": "ok", "confidence": 0.1},
            ConfidenceResponse,
            LOCAL,
        )
        is False
    )
    assert (
        EscalationPolicy(confidence_threshold=0.9).should_verify_after(
            {"summary": "ok", "confidence": "low"},
            ExampleResponse,
            LOCAL,
        )
        is False
    )
    assert (
        EscalationPolicy(confidence_threshold=0.9).should_verify_after(
            {"summary": "ok"},
            ExampleResponse,
            LOCAL,
        )
        is False
    )


def test_gateway_pre_call_override_uses_cloud_path_and_marks_escalated() -> None:
    cloud_client = SpyLLMClient([{"summary": "cloud"}], provider_name="cloud-spy")
    local_client = SpyLLMClient([{"summary": "local"}], provider_name="local-spy")
    budget = SpyCallBudget()
    gateway = LLMGateway(
        {CLOUD: cloud_client, LOCAL: local_client},
        router=local_router(),
        call_budget=cast(DailyCallBudget, budget),
        escalation_policy=EscalationPolicy(),
    )

    result = gateway.complete_json(
        LLMTaskType.PORTFOLIO_BRIEFING,
        PublicPayload(value="safe"),
        ExampleResponse,
        "brief",
        escalation_signal=EscalationSignal(risk_level=RiskLevel.HIGH),
    )

    assert result.output == {"summary": "cloud"}
    assert result.provider == "cloud-spy"
    assert result.escalated is True
    assert len(cloud_client.calls) == 1
    assert local_client.calls == []
    assert budget.calls == 1
    assert json.loads(cloud_client.calls[0][1].content) == {"value": "safe"}


def test_gateway_pre_call_override_skips_payload_that_is_not_cloudsafe(
    caplog: pytest.LogCaptureFixture,
) -> None:
    cloud_client = SpyLLMClient([{"summary": "cloud"}], provider_name="cloud-spy")
    local_client = SpyLLMClient([{"summary": "local"}], provider_name="local-spy")
    gateway = LLMGateway(
        {CLOUD: cloud_client, LOCAL: local_client},
        router=local_router(),
        escalation_policy=EscalationPolicy(),
    )

    result = gateway.complete_json(
        LLMTaskType.PORTFOLIO_BRIEFING,
        RawPayload(value="raw"),
        ExampleResponse,
        "brief",
        escalation_signal=EscalationSignal(risk_level=RiskLevel.HIGH),
    )

    assert result.output == {"summary": "local"}
    assert result.provider == "local-spy"
    assert result.escalated is False
    assert cloud_client.calls == []
    assert len(local_client.calls) == 1
    assert "reason=cloud_boundary" in caplog.text


def test_gateway_does_not_override_when_signal_is_none() -> None:
    cloud_client = SpyLLMClient([{"summary": "cloud"}], provider_name="cloud-spy")
    local_client = SpyLLMClient([{"summary": "local"}], provider_name="local-spy")
    gateway = LLMGateway(
        {CLOUD: cloud_client, LOCAL: local_client},
        router=local_router(),
        escalation_policy=EscalationPolicy(),
    )

    result = gateway.complete_json(
        LLMTaskType.PORTFOLIO_BRIEFING,
        PublicPayload(value="safe"),
        ExampleResponse,
        "brief",
    )

    assert result.output == {"summary": "local"}
    assert result.provider == "local-spy"
    assert result.escalated is False
    assert cloud_client.calls == []
    assert len(local_client.calls) == 1


def test_gateway_post_call_verification_replaces_result_without_cache() -> None:
    local_client = SpyLLMClient(
        [{"summary": "local", "confidence": 0.2}],
        provider_name="local-spy",
    )
    cloud_client = SpyLLMClient(
        [{"summary": "cloud", "confidence": 0.95}],
        provider_name="cloud-spy",
    )
    budget = SpyCallBudget()
    cache = SpyResponseCache()
    gateway = LLMGateway(
        {CLOUD: cloud_client, LOCAL: local_client},
        router=local_router(),
        call_budget=cast(DailyCallBudget, budget),
        response_cache=cast(LLMResponseCache, cache),
        escalation_policy=EscalationPolicy(confidence_threshold=0.7),
    )

    result = gateway.complete_json(
        LLMTaskType.PORTFOLIO_BRIEFING,
        PublicPayload(value="safe"),
        ConfidenceResponse,
        "brief",
    )

    assert result.output == {"summary": "cloud", "confidence": 0.95}
    assert result.provider == "cloud-spy"
    assert result.escalated is True
    assert len(local_client.calls) == 1
    assert len(cloud_client.calls) == 1
    assert budget.calls == 1
    assert cache.build_calls == 0
    assert cache.lookup_calls == 0
    assert cache.store_calls == 0


def test_gateway_post_call_verification_failure_returns_original_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    local_client = SpyLLMClient(
        [{"summary": "local", "confidence": 0.2}],
        provider_name="local-spy",
        model_name="local-model",
    )
    cloud_client = SpyLLMClient(
        [{"confidence": 0.95}],
        provider_name="cloud-spy",
    )
    gateway = LLMGateway(
        {CLOUD: cloud_client, LOCAL: local_client},
        router=local_router(),
        escalation_policy=EscalationPolicy(confidence_threshold=0.7),
    )

    result = gateway.complete_json(
        LLMTaskType.PORTFOLIO_BRIEFING,
        PublicPayload(value="safe"),
        ConfidenceResponse,
        "brief",
    )

    assert result.output == {"summary": "local", "confidence": 0.2}
    assert result.provider == "local-spy"
    assert result.model_name == "local-model"
    assert result.escalated is True
    assert "schema_validation" in caplog.text


def test_gateway_post_call_verification_exception_returns_original_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    local_client = SpyLLMClient(
        [{"summary": "local", "confidence": 0.2}],
        provider_name="local-spy",
    )
    cloud_client = SpyLLMClient(
        provider_name="cloud-spy",
        error=RuntimeError("cloud failed"),
    )
    gateway = LLMGateway(
        {CLOUD: cloud_client, LOCAL: local_client},
        router=local_router(),
        escalation_policy=EscalationPolicy(confidence_threshold=0.7),
    )

    result = gateway.complete_json(
        LLMTaskType.PORTFOLIO_BRIEFING,
        PublicPayload(value="safe"),
        ConfidenceResponse,
        "brief",
    )

    assert result.output == {"summary": "local", "confidence": 0.2}
    assert result.escalated is True
    assert "reason=exception" in caplog.text


def test_gateway_post_call_verification_budget_failure_keeps_escalated_false(
    caplog: pytest.LogCaptureFixture,
) -> None:
    local_client = SpyLLMClient(
        [{"summary": "local", "confidence": 0.2}],
        provider_name="local-spy",
    )
    cloud_client = SpyLLMClient(
        [{"summary": "cloud", "confidence": 0.95}],
        provider_name="cloud-spy",
    )
    budget = FailingCallBudget()
    gateway = LLMGateway(
        {CLOUD: cloud_client, LOCAL: local_client},
        router=local_router(),
        call_budget=cast(DailyCallBudget, budget),
        escalation_policy=EscalationPolicy(confidence_threshold=0.7),
    )

    result = gateway.complete_json(
        LLMTaskType.PORTFOLIO_BRIEFING,
        PublicPayload(value="safe"),
        ConfidenceResponse,
        "brief",
    )

    assert result.output == {"summary": "local", "confidence": 0.2}
    assert result.provider == "local-spy"
    assert result.escalated is False
    assert len(local_client.calls) == 1
    assert cloud_client.calls == []
    assert budget.calls == 1
    assert "reason=exception" in caplog.text


def test_gateway_post_call_verification_boundary_failure_keeps_escalated_false(
    caplog: pytest.LogCaptureFixture,
) -> None:
    local_client = SpyLLMClient(
        [{"summary": "local", "confidence": 0.2}],
        provider_name="local-spy",
    )
    cloud_client = SpyLLMClient(
        [{"summary": "cloud", "confidence": 0.95}],
        provider_name="cloud-spy",
    )
    gateway = LLMGateway(
        {CLOUD: cloud_client, LOCAL: local_client},
        router=local_router(),
        escalation_policy=EscalationPolicy(confidence_threshold=0.7),
    )

    result = gateway.complete_json(
        LLMTaskType.PORTFOLIO_BRIEFING,
        RawPayload(value="raw"),
        ConfidenceResponse,
        "brief",
    )

    assert result.output == {"summary": "local", "confidence": 0.2}
    assert result.provider == "local-spy"
    assert result.escalated is False
    assert len(local_client.calls) == 1
    assert cloud_client.calls == []
    assert "reason=exception" in caplog.text


def test_gateway_post_call_skips_verification_when_first_provider_is_cloud() -> None:
    cloud_client = SpyLLMClient(
        [{"summary": "cloud", "confidence": 0.2}],
        provider_name="cloud-spy",
    )
    gateway = LLMGateway(
        {CLOUD: cloud_client},
        escalation_policy=EscalationPolicy(confidence_threshold=0.7),
    )

    result = gateway.complete_json(
        LLMTaskType.PORTFOLIO_BRIEFING,
        PublicPayload(value="safe"),
        ConfidenceResponse,
        "brief",
    )

    assert result.output == {"summary": "cloud", "confidence": 0.2}
    assert result.escalated is False
    assert len(cloud_client.calls) == 1


def test_gateway_without_policy_preserves_existing_local_result() -> None:
    local_client = SpyLLMClient(
        [{"summary": "local", "confidence": 0.2}],
        provider_name="local-spy",
    )
    cloud_client = SpyLLMClient(
        [{"summary": "cloud", "confidence": 0.95}],
        provider_name="cloud-spy",
    )
    gateway = LLMGateway(
        {CLOUD: cloud_client, LOCAL: local_client},
        router=local_router(),
    )

    result = gateway.complete_json(
        LLMTaskType.PORTFOLIO_BRIEFING,
        PublicPayload(value="safe"),
        ConfidenceResponse,
        "brief",
    )

    assert result.output == {"summary": "local", "confidence": 0.2}
    assert result.escalated is False
    assert cloud_client.calls == []


def test_gateway_post_call_skip_without_cloud_client_keeps_escalated_false(
    caplog: pytest.LogCaptureFixture,
) -> None:
    local_client = SpyLLMClient(
        [{"summary": "local", "confidence": 0.2}],
        provider_name="local-spy",
    )
    gateway = LLMGateway(
        {LOCAL: local_client},
        router=local_router(),
        escalation_policy=EscalationPolicy(confidence_threshold=0.7),
    )

    result = gateway.complete_json(
        LLMTaskType.PORTFOLIO_BRIEFING,
        PublicPayload(value="safe"),
        ConfidenceResponse,
        "brief",
    )

    assert result.output == {"summary": "local", "confidence": 0.2}
    assert result.escalated is False
    assert "reason=cloud_client_missing" in caplog.text
