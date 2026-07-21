from typing import Any

from pydantic import BaseModel, Field

from app.core.schema import UtcDatetime
from app.domains.decision_logs.types import (
    ConfidenceLevel,
    CreatedBy,
    DecisionType,
    EvidenceRelationship,
    ReviewTriggerType,
    RiskSeverity,
    TargetType,
)


class DecisionTarget(BaseModel):
    type: TargetType
    id: str = Field(min_length=1, max_length=64)
    label: str | None = None


class DecisionEvidenceInput(BaseModel):
    type: str = Field(min_length=1, max_length=30)
    id: str | None = Field(default=None, max_length=64)
    version: int | None = None
    title: str | None = Field(default=None, max_length=255)
    summary: str | None = None
    snapshot: dict[str, Any] | None = None
    relationship: EvidenceRelationship = EvidenceRelationship.SUPPORTING


class DecisionRiskInput(BaseModel):
    type: str = Field(min_length=1, max_length=40)
    severity: RiskSeverity
    description: str | None = None


class DecisionReviewTriggerInput(BaseModel):
    type: ReviewTriggerType
    condition: dict[str, Any]
    scheduled_at: UtcDatetime | None = None


class DecisionSnapshotInput(BaseModel):
    snapshot_type: str = Field(min_length=1, max_length=30)
    data: dict[str, Any]


class DecisionLogCreate(BaseModel):
    target: DecisionTarget
    decision_type: DecisionType
    thesis: str | None = None
    rationale: str | None = None
    confidence_level: ConfidenceLevel | None = None
    supporting_reasons: list[str] = Field(default_factory=list)
    counter_arguments: list[str] = Field(default_factory=list)
    risks: list[DecisionRiskInput] = Field(default_factory=list)
    evidence: list[DecisionEvidenceInput] = Field(default_factory=list)
    review_triggers: list[DecisionReviewTriggerInput] = Field(default_factory=list)
    created_by: CreatedBy = CreatedBy.USER


class DecisionLogUpdate(BaseModel):
    target: DecisionTarget | None = None
    decision_type: DecisionType | None = None
    thesis: str | None = None
    rationale: str | None = None
    confidence_level: ConfidenceLevel | None = None
    created_by: CreatedBy | None = None


class DecisionActivateRequest(BaseModel):
    snapshots: list[DecisionSnapshotInput] = Field(default_factory=list)


class DecisionEvidenceResponse(BaseModel):
    id: int
    type: str
    evidence_id: str | None = None
    version: int | None = None
    title: str
    summary: str | None = None
    snapshot: dict[str, Any] | None = None
    relationship: str
    created_at: UtcDatetime


class DecisionRiskResponse(BaseModel):
    id: int
    type: str
    description: str | None = None
    severity: str
    created_at: UtcDatetime


class DecisionReviewTriggerResponse(BaseModel):
    id: int
    type: str
    condition: dict[str, Any]
    scheduled_at: UtcDatetime | None = None
    status: str
    triggered_at: UtcDatetime | None = None
    created_at: UtcDatetime


class DecisionSnapshotResponse(BaseModel):
    id: int
    snapshot_type: str
    data: dict[str, Any]
    captured_at: UtcDatetime


class DecisionLogResponse(BaseModel):
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
    risks: list[DecisionRiskResponse]
    evidence: list[DecisionEvidenceResponse]
    review_triggers: list[DecisionReviewTriggerResponse]


class DecisionLogDetailResponse(DecisionLogResponse):
    snapshots: list[DecisionSnapshotResponse]


class DecisionTypeDistributionItem(BaseModel):
    type: DecisionType
    count: int
    share: float


class DecisionOverviewResponse(BaseModel):
    total_count: int
    created_this_week: int
    review_due_count: int
    active_count: int
    decision_type_distribution: list[DecisionTypeDistributionItem]
    as_of: UtcDatetime
