from datetime import datetime

from pydantic import BaseModel, HttpUrl


class ResearchSummarySource(BaseModel):
    type: str
    label: str
    url: HttpUrl | None = None


class ResearchSummaryResponse(BaseModel):
    asset_id: int
    positive_factors: list[str]
    negative_factors: list[str]
    items_to_verify: list[str]
    sources: list[ResearchSummarySource]
    updated_at: datetime
