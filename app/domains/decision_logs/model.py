from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.domains.decision_logs.types import (
    CreatedBy,
    DecisionStatus,
    ReviewTriggerStatus,
)


class DecisionLog(Base, TimestampMixin):
    __tablename__ = "decision_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(20), nullable=True)
    decision_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=DecisionStatus.DRAFT.value,
        server_default=DecisionStatus.DRAFT.value,
    )
    thesis: Mapped[str | None] = mapped_column(Text, nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_level: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_by: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=CreatedBy.USER.value,
        server_default=CreatedBy.USER.value,
    )
    superseded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("decision_logs.id"),
        nullable=True,
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class DecisionEvidence(Base, TimestampMixin):
    __tablename__ = "decision_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    decision_id: Mapped[int] = mapped_column(
        ForeignKey("decision_logs.id"), nullable=False
    )
    evidence_type: Mapped[str] = mapped_column(String(30), nullable=False)
    evidence_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    evidence_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    relationship: Mapped[str] = mapped_column(String(20), nullable=False)


class DecisionRisk(Base, TimestampMixin):
    __tablename__ = "decision_risks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    decision_id: Mapped[int] = mapped_column(
        ForeignKey("decision_logs.id"), nullable=False
    )
    risk_type: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)


class DecisionReviewTrigger(Base, TimestampMixin):
    __tablename__ = "decision_review_triggers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    decision_id: Mapped[int] = mapped_column(
        ForeignKey("decision_logs.id"), nullable=False
    )
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False)
    condition: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ReviewTriggerStatus.PENDING.value,
        server_default=ReviewTriggerStatus.PENDING.value,
    )
    triggered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class DecisionSnapshot(Base, TimestampMixin):
    __tablename__ = "decision_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    decision_id: Mapped[int] = mapped_column(
        ForeignKey("decision_logs.id"), nullable=False
    )
    snapshot_type: Mapped[str] = mapped_column(String(30), nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class DecisionReview(Base, TimestampMixin):
    __tablename__ = "decision_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    decision_id: Mapped[int] = mapped_column(
        ForeignKey("decision_logs.id"), nullable=False
    )
    outcome_status: Mapped[str] = mapped_column(String(30), nullable=False)
    thesis_result: Mapped[str] = mapped_column(String(30), nullable=False)
    process_quality: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    result_metrics: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    what_went_well: Mapped[str | None] = mapped_column(Text, nullable=True)
    what_was_missed: Mapped[str | None] = mapped_column(Text, nullable=True)
    what_to_change: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
