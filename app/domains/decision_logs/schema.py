from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.core.schema import UtcDatetime
from app.domains.decision_logs.types import CreatedBy, DecisionStatus, DecisionType


class DecisionLogCreate(BaseModel):
    ticker: str = Field(max_length=20)
    decision_type: DecisionType
    company_name: str | None = Field(default=None, max_length=255)
    decision_status: DecisionStatus = DecisionStatus.OPEN
    summary: str | None = None
    reason: str | None = None
    risk_note: str | None = None
    action_plan: str | None = None
    confidence_score: int | None = Field(default=None, ge=0, le=100)
    target_price: Decimal | None = None
    stop_loss_price: Decimal | None = None
    valuation_snapshot: dict[str, Any] | None = None
    news_snapshot: dict[str, Any] | None = None
    portfolio_snapshot: dict[str, Any] | None = None
    ai_analysis_snapshot: dict[str, Any] | None = None
    cognitive_risks: list[str] = Field(default_factory=list)
    created_by: CreatedBy = CreatedBy.USER
    decided_at: datetime | None = None


class DecisionLogUpdate(BaseModel):
    ticker: str | None = Field(default=None, max_length=20)
    decision_type: DecisionType | None = None
    company_name: str | None = Field(default=None, max_length=255)
    decision_status: DecisionStatus | None = None
    summary: str | None = None
    reason: str | None = None
    risk_note: str | None = None
    action_plan: str | None = None
    confidence_score: int | None = Field(default=None, ge=0, le=100)
    target_price: Decimal | None = None
    stop_loss_price: Decimal | None = None
    valuation_snapshot: dict[str, Any] | None = None
    news_snapshot: dict[str, Any] | None = None
    portfolio_snapshot: dict[str, Any] | None = None
    ai_analysis_snapshot: dict[str, Any] | None = None
    cognitive_risks: list[str] | None = None
    created_by: CreatedBy | None = None
    decided_at: datetime | None = None
    reviewed_at: datetime | None = None
    closed_at: datetime | None = None


class DecisionLogResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    user_id: int
    ticker: str
    company_name: str | None = None
    decision_type: str
    decision_status: str
    summary: str | None = None
    reason: str | None = None
    risk_note: str | None = None
    action_plan: str | None = None
    confidence_score: int | None = None
    target_price: Decimal | None = None
    stop_loss_price: Decimal | None = None
    valuation_snapshot: dict[str, Any] | None = None
    news_snapshot: dict[str, Any] | None = None
    portfolio_snapshot: dict[str, Any] | None = None
    ai_analysis_snapshot: dict[str, Any] | None = None
    cognitive_risks: list[str] = Field(default_factory=list)
    created_by: str
    decided_at: UtcDatetime
    reviewed_at: UtcDatetime | None = None
    closed_at: UtcDatetime | None = None
    created_at: UtcDatetime
    updated_at: UtcDatetime
