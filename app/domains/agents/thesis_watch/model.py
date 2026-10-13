from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ThesisCheck(Base):
    __tablename__ = "thesis_checks"
    __table_args__ = (
        UniqueConstraint(
            "decision_id", "check_date", name="uq_thesis_checks_decision_date"
        ),
        Index("ix_thesis_checks_user_date", "user_id", "check_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    decision_id: Mapped[int] = mapped_column(ForeignKey("decision_logs.id"))
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"))
    check_date: Mapped[date] = mapped_column(Date)
    verdict: Mapped[str] = mapped_column(String(20))
    max_severity: Mapped[str | None] = mapped_column(String(10), nullable=True)
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
