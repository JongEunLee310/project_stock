from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    thesis_id: Mapped[int | None] = mapped_column(
        ForeignKey("investment_theses.id"), nullable=True
    )
    news_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("news_items.id"), nullable=True
    )
    signal_type: Mapped[str] = mapped_column(String(20), index=True)
    score: Mapped[int]
    risk_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
