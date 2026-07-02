from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.adapters.llm.types import LLMTaskType, RiskLevel


class SuggestedAction(str, Enum):
    BUY_WATCH = "buy_watch"
    HOLD = "hold"
    TRIM_WATCH = "trim_watch"
    AVOID = "avoid"
    NEED_MORE_DATA = "need_more_data"


class RunStatus(str, Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class LLMAnalysisResult(BaseModel):
    summary: str
    risk_level: RiskLevel
    suggested_action: SuggestedAction
    reasons: list[str]
    watch_points: list[str]
    counter_arguments: list[str]
    data_limitations: list[str]
    confidence: float = Field(ge=0.0, le=1.0)


class LLMAnalysisRunCreate(BaseModel):
    user_id: int
    task_type: LLMTaskType
    related_symbols: list[str]
    input_context_json: dict[str, Any]
    output_json: dict[str, Any] | None = None
    status: RunStatus = RunStatus.PENDING
    model_name: str | None = None
    prompt_version: str | None = None
    provider: str | None = None
    related_decision_log_id: int | None = None
    error_message: str | None = None


class LLMAnalysisRunResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    user_id: int
    task_type: str
    related_symbols: list[str]
    input_context_json: dict[str, Any]
    output_json: dict[str, Any] | None
    status: str
    model_name: str | None
    prompt_version: str | None
    provider: str | None
    related_decision_log_id: int | None
    error_message: str | None
