from dataclasses import FrozenInstanceError
from typing import Any

import pytest
from pydantic import BaseModel

from app.adapters.llm.escalation import EscalationPolicy, EscalationSignal
from app.adapters.llm.gateway import CLOUD, LOCAL
from app.adapters.llm.types import RiskLevel


class SummaryResponse(BaseModel):
    summary: str


class ConfidenceResponse(BaseModel):
    summary: str
    confidence: float


def test_escalation_signal_defaults_and_frozen() -> None:
    signal = EscalationSignal()

    assert signal.risk_level == RiskLevel.LOW
    assert signal.loss_spike is False
    assert signal.news_sentiment_swing is False
    assert signal.event_flag is False
    assert signal.trade_question is False
    with pytest.raises(FrozenInstanceError):
        setattr(signal, "loss_spike", True)


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
def test_policy_escalates_local_route_for_each_pre_call_trigger(
    signal: EscalationSignal,
) -> None:
    policy = EscalationPolicy()

    assert policy.should_escalate_before(signal, LOCAL) is True


def test_policy_does_not_escalate_local_route_without_trigger() -> None:
    policy = EscalationPolicy()

    assert policy.should_escalate_before(EscalationSignal(), LOCAL) is False


def test_policy_does_not_escalate_cloud_route_even_with_trigger() -> None:
    policy = EscalationPolicy()

    assert (
        policy.should_escalate_before(
            EscalationSignal(risk_level=RiskLevel.HIGH),
            CLOUD,
        )
        is False
    )


def test_policy_does_not_escalate_medium_risk_level() -> None:
    policy = EscalationPolicy()

    assert (
        policy.should_escalate_before(
            EscalationSignal(risk_level=RiskLevel.MEDIUM),
            LOCAL,
        )
        is False
    )


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ({"summary": "ok", "confidence": 0.49}, True),
        ({"summary": "ok", "confidence": 0.5}, False),
        ({"summary": "ok", "confidence": 0.8}, False),
    ],
)
def test_policy_verifies_after_for_confidence_below_threshold(
    output: dict[str, Any],
    expected: bool,
) -> None:
    policy = EscalationPolicy(confidence_threshold=0.5)

    assert policy.should_verify_after(output, ConfidenceResponse, LOCAL) is expected


def test_policy_verifies_after_for_schema_validation_failure() -> None:
    policy = EscalationPolicy()

    assert policy.should_verify_after({}, SummaryResponse, LOCAL) is True


def test_policy_does_not_verify_after_when_schema_passes() -> None:
    policy = EscalationPolicy()

    assert (
        policy.should_verify_after({"summary": "ok"}, SummaryResponse, LOCAL) is False
    )


def test_policy_does_not_verify_after_cloud_first_provider() -> None:
    policy = EscalationPolicy(confidence_threshold=0.5)

    assert (
        policy.should_verify_after({}, SummaryResponse, CLOUD)
        is False
    )
    assert (
        policy.should_verify_after(
            {"summary": "ok", "confidence": 0.1},
            ConfidenceResponse,
            CLOUD,
        )
        is False
    )


def test_policy_ignores_confidence_when_threshold_is_none() -> None:
    policy = EscalationPolicy(confidence_threshold=None)

    assert (
        policy.should_verify_after(
            {"summary": "ok", "confidence": 0.1},
            ConfidenceResponse,
            LOCAL,
        )
        is False
    )


@pytest.mark.parametrize("confidence", [None, "low", True])
def test_policy_ignores_missing_or_non_numeric_confidence(
    confidence: object,
) -> None:
    policy = EscalationPolicy(confidence_threshold=0.5)
    output: dict[str, Any] = {"summary": "ok"}
    if confidence is not None:
        output["confidence"] = confidence

    assert policy.should_verify_after(output, SummaryResponse, LOCAL) is False
