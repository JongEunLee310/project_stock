from typing import Any

from sqlalchemy import ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.domains.llm_analysis.schema import RunStatus


class LLMAnalysisRun(Base, TimestampMixin):
    __tablename__ = "llm_analysis_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    task_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    related_symbols: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    input_context_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    output_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        default=RunStatus.PENDING.value,
        server_default=RunStatus.PENDING.value,
    )
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    related_decision_log_id: Mapped[int | None] = mapped_column(
        ForeignKey("decision_logs.id"),
        nullable=True,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
