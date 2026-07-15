from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class AlertRule(Base, TimestampMixin):
    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(20))
    template_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_type: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    condition: Mapped[dict[str, Any]] = mapped_column(JSON)
    severity: Mapped[str] = mapped_column(String(20))
    channels: Mapped[list[str]] = mapped_column(JSON)
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        index=True,
    )
    cooldown_seconds: Mapped[int] = mapped_column(Integer)
    delivery_policy: Mapped[str] = mapped_column(String(30))
    last_triggered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
