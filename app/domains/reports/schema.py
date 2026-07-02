import json
from typing import Any

from pydantic import BaseModel, Field, computed_field, field_validator

from app.core.schema import UtcDatetime


class ResearchReportCreate(BaseModel):
    asset_id: int
    thesis_id: int | None = None
    summary: str
    positive_factors: list[str] | None = None
    negative_factors: list[str] | None = None
    risk_level: str | None = Field(default=None, max_length=20)
    thesis_conflict_status: str | None = Field(default=None, max_length=20)
    conflict_reason: str | None = None
    news_item_ids: list[int] | None = None


class ResearchReportResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    asset_id: int
    thesis_id: int | None
    summary: str
    positive_factors: list[str] | None
    negative_factors: list[str] | None
    risk_level: str | None
    thesis_conflict_status: str | None
    conflict_reason: str | None
    news_item_ids: list[int] | None
    source: str | None = None
    created_at: UtcDatetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def title(self) -> str:
        return _title_from_summary(self.summary, fallback="Research report")

    @field_validator(
        "positive_factors",
        "negative_factors",
        "news_item_ids",
        mode="before",
    )
    @classmethod
    def parse_json_array(cls, value: Any) -> Any:
        if value is None or isinstance(value, list):
            return value
        if isinstance(value, str):
            return json.loads(value)
        return value


def _title_from_summary(summary: str, *, fallback: str) -> str:
    title = next((line.strip() for line in summary.splitlines() if line.strip()), "")
    return title or fallback
