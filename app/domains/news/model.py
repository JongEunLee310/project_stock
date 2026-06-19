from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class NewsItem(Base, TimestampMixin):
    __tablename__ = "news_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    raw_news_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_news_events.id"), nullable=True
    )
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    title: Mapped[str] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(String(2048))
    source: Mapped[str] = mapped_column(String(100))
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    sentiment: Mapped[str | None] = mapped_column(String(20), nullable=True)
    impact_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    positive_factors: Mapped[str | None] = mapped_column(Text, nullable=True)
    negative_factors: Mapped[str | None] = mapped_column(Text, nullable=True)
