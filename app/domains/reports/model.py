from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ResearchReport(Base, TimestampMixin):
    __tablename__ = "research_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    thesis_id: Mapped[int | None] = mapped_column(
        ForeignKey("investment_theses.id"), nullable=True
    )
    summary: Mapped[str] = mapped_column(Text)
    positive_factors: Mapped[str | None] = mapped_column(Text, nullable=True)
    negative_factors: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    thesis_conflict_status: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )
    conflict_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    news_item_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
