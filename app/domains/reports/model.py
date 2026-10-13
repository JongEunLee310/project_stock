from datetime import date
from typing import Any

from sqlalchemy import JSON, Date, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.domains.reports.types import ReportType


class ResearchReport(Base, TimestampMixin):
    __tablename__ = "research_reports"
    __table_args__ = (
        Index(
            "uq_research_reports_daily_brief",
            "asset_id",
            "brief_date",
            unique=True,
            postgresql_where=text("report_type = 'DAILY_BRIEF'"),
            sqlite_where=text("report_type = 'DAILY_BRIEF'"),
        ),
        Index(
            "uq_research_reports_source_ref",
            "asset_id",
            "report_type",
            "source_ref",
            unique=True,
            postgresql_where=text("source_ref IS NOT NULL"),
            sqlite_where=text("source_ref IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    report_type: Mapped[str] = mapped_column(
        String(20),
        default=ReportType.ARTICLE.value,
        server_default=ReportType.ARTICLE.value,
        nullable=False,
    )
    source_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    brief_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    content: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
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
