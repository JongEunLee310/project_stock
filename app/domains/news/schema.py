from datetime import datetime

from pydantic import BaseModel, Field


class NewsItemCreate(BaseModel):
    raw_news_event_id: int | None = None
    asset_id: int
    title: str = Field(max_length=500)
    url: str = Field(max_length=2048)
    source: str = Field(max_length=100)
    published_at: datetime | None = None
    summary: str | None = None
    sentiment: str | None = Field(default=None, max_length=20)
    impact_level: str | None = Field(default=None, max_length=20)


class NewsItemResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    raw_news_event_id: int | None
    asset_id: int
    title: str
    url: str
    source: str
    published_at: datetime | None
    summary: str | None
    sentiment: str | None
    impact_level: str | None
    created_at: datetime
