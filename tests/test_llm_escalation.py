from typing import Any

import pytest
from pydantic import BaseModel

from app.adapters.llm.escalation import EscalationPolicy, EscalationTrigger
from app.adapters.llm.types import RiskLevel


class ConfidenceResponse(BaseModel):
    summary: str
    confidence: float


@pytest.mark.parametrize("risk_level", [RiskLevel.LOW, RiskLevel.MEDIUM])
def test_escalation_policy_pre_call_ignores_non_high_risk(
    risk_level: RiskLevel,
) -> None:
    policy = EscalationPolicy(confidence_threshold=0.7)

    assert policy.evaluate_pre_call(risk_level) is None


def test_escalation_policy_pre_call_escalates_high_risk() -> None:
    policy = EscalationPolicy(confidence_threshold=0.7)

    assert policy.evaluate_pre_call(RiskLevel.HIGH) == EscalationTrigger.HIGH_RISK_INPUT


def test_escalation_policy_post_call_escalates_schema_validation_failure() -> None:
    policy = EscalationPolicy(confidence_threshold=0.7)

    trigger = policy.evaluate_post_call({"summary": "missing confidence"}, ConfidenceResponse)

    assert trigger == EscalationTrigger.SCHEMA_VALIDATION_FAILED


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ({"summary": "ok", "confidence": 0.69}, EscalationTrigger.LOW_CONFIDENCE),
        ({"summary": "ok", "confidence": 0.7}, None),
        ({"summary": "ok", "confidence": 0.91}, None),
    ],
)
def test_escalation_policy_post_call_evaluates_confidence_threshold(
    output: dict[str, Any],
    expected: EscalationTrigger | None,
) -> None:
    policy = EscalationPolicy(confidence_threshold=0.7)

    assert policy.evaluate_post_call(output, ConfidenceResponse) == expected


def test_escalation_policy_post_call_ignores_missing_confidence_when_schema_allows_it() -> None:
    class OptionalConfidenceResponse(BaseModel):
        summary: str

    policy = EscalationPolicy(confidence_threshold=0.7)

    trigger = policy.evaluate_post_call(
        {"summary": "ok"},
        OptionalConfidenceResponse,
    )

    assert trigger is None
