from datetime import datetime

from pydantic import BaseModel, Field

from app.core.schema import UtcDatetime
from app.domains.decision_logs.types import (
    ConfidenceLevel,
    CreatedBy,
    DecisionStatus,
    DecisionType,
    TargetType,
)


class DecisionLogCreate(BaseModel):
    target_type: TargetType
    target_id: str = Field(max_length=64)
    symbol: str | None = Field(default=None, max_length=20)
    decision_type: DecisionType
    status: DecisionStatus = DecisionStatus.DRAFT
    thesis: str | None = None
    rationale: str | None = None
    confidence_level: ConfidenceLevel | None = None
    created_by: CreatedBy = CreatedBy.USER
    superseded_by_id: int | None = None
    decided_at: datetime | None = None
    activated_at: datetime | None = None
    reviewed_at: datetime | None = None
    closed_at: datetime | None = None


class DecisionLogUpdate(BaseModel):
    target_type: TargetType | None = None
    target_id: str | None = Field(default=None, max_length=64)
    symbol: str | None = Field(default=None, max_length=20)
    decision_type: DecisionType | None = None
    status: DecisionStatus | None = None
    thesis: str | None = None
    rationale: str | None = None
    confidence_level: ConfidenceLevel | None = None
    created_by: CreatedBy | None = None
    superseded_by_id: int | None = None
    decided_at: datetime | None = None
    activated_at: datetime | None = None
    reviewed_at: datetime | None = None
    closed_at: datetime | None = None


class DecisionLogResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    user_id: int
    target_type: str
    target_id: str
    symbol: str | None = None
    decision_type: str
    status: str
    thesis: str | None = None
    rationale: str | None = None
    confidence_level: str | None = None
    created_by: str
    superseded_by_id: int | None = None
    decided_at: UtcDatetime | None = None
    activated_at: UtcDatetime | None = None
    reviewed_at: UtcDatetime | None = None
    closed_at: UtcDatetime | None = None
    created_at: UtcDatetime
    updated_at: UtcDatetime


class ReviewedDecisionItem(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    symbol: str | None = None
    decision_type: str
    rationale: str | None = None
    reviewed_at: UtcDatetime


class DecisionLogStatsResponse(BaseModel):
    decision_type_counts: dict[str, int]
    total: int
    recent_reviewed: list[ReviewedDecisionItem]
