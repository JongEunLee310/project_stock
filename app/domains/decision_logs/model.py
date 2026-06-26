from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.domains.decision_logs.types import CreatedBy, DecisionStatus


class DecisionLog(Base, TimestampMixin):
    __tablename__ = "decision_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decision_type: Mapped[str] = mapped_column(String(30), nullable=False)
    decision_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=DecisionStatus.OPEN.value,
        server_default=DecisionStatus.OPEN.value,
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    stop_loss_price: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 4),
        nullable=True,
    )
    valuation_snapshot: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    news_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    portfolio_snapshot: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    ai_analysis_snapshot: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    cognitive_risks: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        server_default="[]",
    )
    created_by: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=CreatedBy.USER.value,
        server_default=CreatedBy.USER.value,
    )
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
