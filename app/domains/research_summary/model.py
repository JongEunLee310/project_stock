from typing import Any

from sqlalchemy import ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ResearchSummaryRow(Base, TimestampMixin):
    __tablename__ = "research_summaries"
    __table_args__ = (
        UniqueConstraint("asset_id", name="uq_research_summaries_asset"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"))
    stance: Mapped[str] = mapped_column(String(50))
    stance_confidence: Mapped[str] = mapped_column(String(20))
    stance_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    headline: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    positive_factors: Mapped[list[str]] = mapped_column(
        JSON, default=list, server_default="[]"
    )
    caution_factors: Mapped[list[str]] = mapped_column(
        JSON, default=list, server_default="[]"
    )
    next_checks: Mapped[list[str]] = mapped_column(
        JSON, default=list, server_default="[]"
    )
    counter_points: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, server_default="[]"
    )
    confidence_basis: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_risks: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
