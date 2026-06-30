from dataclasses import FrozenInstanceError

import pytest

from app.adapters.llm.types import (
    CachePolicy,
    LLMRequest,
    LLMResponse,
    LLMTaskType,
    RiskLevel,
    SensitivityLevel,
    TokenUsage,
    ValidationStatus,
)


def test_llm_task_type_values_match_contract() -> None:
    assert {member.name: member.value for member in LLMTaskType} == {
        "NEWS_SUMMARY": "NEWS_SUMMARY",
        "THESIS_CONFLICT": "THESIS_CONFLICT",
        "PORTFOLIO_BRIEFING": "PORTFOLIO_BRIEFING",
        "DASHBOARD_BRIEFING": "DASHBOARD_BRIEFING",
        "WATCHLIST_NOTE": "WATCHLIST_NOTE",
        "TAG_SENTIMENT": "TAG_SENTIMENT",
        "AGENT": "AGENT",
    }


def test_sensitivity_level_values_match_contract() -> None:
    assert {member.name: member.value for member in SensitivityLevel} == {
        "RAW": "RAW",
        "SEMI": "SEMI",
        "AGGREGATED": "AGGREGATED",
        "PUBLIC": "PUBLIC",
    }


def test_risk_level_values_match_contract() -> None:
    assert {member.name: member.value for member in RiskLevel} == {
        "LOW": "LOW",
        "MEDIUM": "MEDIUM",
        "HIGH": "HIGH",
    }


def test_cache_policy_values_match_contract() -> None:
    assert {member.name: member.value for member in CachePolicy} == {
        "BYPASS": "BYPASS",
        "READ_WRITE": "READ_WRITE",
        "READ_ONLY": "READ_ONLY",
    }


def test_validation_status_values_match_contract() -> None:
    assert {member.name: member.value for member in ValidationStatus} == {
        "NOT_VALIDATED": "NOT_VALIDATED",
        "PASSED": "PASSED",
        "FAILED": "FAILED",
    }


def test_token_usage_is_frozen() -> None:
    token_usage = TokenUsage(
        prompt_tokens=1,
        completion_tokens=2,
        total_tokens=3,
    )

    with pytest.raises(FrozenInstanceError):
        setattr(token_usage, "total_tokens", 4)


def test_llm_request_is_frozen() -> None:
    request = LLMRequest(
        task_type=LLMTaskType.NEWS_SUMMARY,
        system_prompt="Summarize news.",
        sensitivity_level=SensitivityLevel.PUBLIC,
        risk_level=RiskLevel.LOW,
    )

    with pytest.raises(FrozenInstanceError):
        setattr(request, "temperature", 0.2)


def test_llm_response_is_frozen() -> None:
    response = LLMResponse(
        text="summary",
        provider="mock",
        model="test-model",
        latency_ms=10,
    )

    with pytest.raises(FrozenInstanceError):
        setattr(response, "cache_hit", True)


def test_llm_request_defaults_match_contract() -> None:
    request = LLMRequest(
        task_type=LLMTaskType.NEWS_SUMMARY,
        system_prompt="Summarize news.",
        sensitivity_level=SensitivityLevel.PUBLIC,
        risk_level=RiskLevel.LOW,
    )

    assert request.input_payload == {}
    assert request.output_schema is None
    assert request.temperature == 0.0
    assert request.max_tokens is None
    assert request.cache_policy is CachePolicy.BYPASS
    assert request.timeout_ms is None
    assert request.metadata == {}


def test_llm_response_defaults_match_contract() -> None:
    response = LLMResponse(
        text="summary",
        provider="mock",
        model="test-model",
        latency_ms=10,
    )

    assert response.structured_output is None
    assert response.token_usage is None
    assert response.cache_hit is False
    assert response.finish_reason is None
    assert response.validation_status is ValidationStatus.NOT_VALIDATED


def test_llm_request_mutable_defaults_are_not_shared() -> None:
    first_request = LLMRequest(
        task_type=LLMTaskType.NEWS_SUMMARY,
        system_prompt="Summarize news.",
        sensitivity_level=SensitivityLevel.PUBLIC,
        risk_level=RiskLevel.LOW,
    )
    second_request = LLMRequest(
        task_type=LLMTaskType.THESIS_CONFLICT,
        system_prompt="Find conflicts.",
        sensitivity_level=SensitivityLevel.SEMI,
        risk_level=RiskLevel.MEDIUM,
    )

    first_request.input_payload["symbol"] = "AAPL"
    first_request.metadata["trace_id"] = "trace-1"

    assert second_request.input_payload == {}
    assert second_request.metadata == {}
