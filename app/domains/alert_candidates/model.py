from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domains.alert_candidates.types import (
    AlertCandidateStatus,
    AlertCandidateType,
    AlertImportance,
)


class AlertCandidate(Base):
    __tablename__ = "alert_candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    candidate_type: Mapped[str] = mapped_column(String(50), index=True)
    importance: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(
        String(20),
        default=AlertCandidateStatus.UNREAD.value,
        server_default=AlertCandidateStatus.UNREAD.value,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255))
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("assets.id"),
        nullable=True,
        index=True,
    )
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __init__(
        self,
        *,
        user_id: int,
        candidate_type: AlertCandidateType | str,
        importance: AlertImportance | str,
        title: str,
        status: AlertCandidateStatus | str = AlertCandidateStatus.UNREAD,
        message: str | None = None,
        asset_id: int | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        self.user_id = user_id
        self.candidate_type = (
            candidate_type.value
            if isinstance(candidate_type, AlertCandidateType)
            else candidate_type
        )
        self.importance = (
            importance.value if isinstance(importance, AlertImportance) else importance
        )
        self.status = (
            status.value if isinstance(status, AlertCandidateStatus) else status
        )
        self.title = title
        self.message = message
        self.asset_id = asset_id
        self.evidence = evidence
