import json
from typing import Any

from pydantic import BaseModel, Field, field_validator

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
    created_at: UtcDatetime

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
