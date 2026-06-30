from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel


class LLMTaskType(str, Enum):
    NEWS_SUMMARY = "NEWS_SUMMARY"
    THESIS_CONFLICT = "THESIS_CONFLICT"
    PORTFOLIO_BRIEFING = "PORTFOLIO_BRIEFING"
    DASHBOARD_BRIEFING = "DASHBOARD_BRIEFING"
    WATCHLIST_NOTE = "WATCHLIST_NOTE"
    TAG_SENTIMENT = "TAG_SENTIMENT"
    AGENT = "AGENT"


class SensitivityLevel(str, Enum):
    RAW = "RAW"
    SEMI = "SEMI"
    AGGREGATED = "AGGREGATED"
    PUBLIC = "PUBLIC"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class CachePolicy(str, Enum):
    BYPASS = "BYPASS"
    READ_WRITE = "READ_WRITE"
    READ_ONLY = "READ_ONLY"


class ValidationStatus(str, Enum):
    NOT_VALIDATED = "NOT_VALIDATED"
    PASSED = "PASSED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class TokenUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class LLMRequest:
    task_type: LLMTaskType
    system_prompt: str
    sensitivity_level: SensitivityLevel
    risk_level: RiskLevel
    input_payload: dict[str, Any] = field(default_factory=dict)
    output_schema: type[BaseModel] | None = None
    temperature: float = 0.0
    max_tokens: int | None = None
    cache_policy: CachePolicy = CachePolicy.BYPASS
    timeout_ms: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMResponse:
    text: str
    provider: str
    model: str
    latency_ms: int
    structured_output: dict[str, Any] | None = None
    token_usage: TokenUsage | None = None
    cache_hit: bool = False
    finish_reason: str | None = None
    validation_status: ValidationStatus = ValidationStatus.NOT_VALIDATED
