from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.schema import UtcDatetime


NewsCategory = Literal[
    "EARNINGS",
    "PRODUCT",
    "PARTNERSHIP",
    "REGULATION",
    "PERSONNEL",
    "CAPITAL",
    "MARKET",
    "OTHER",
]


class NewsSummaryResult(BaseModel):
    summary: str
    positive_factors: list[str]
    negative_factors: list[str]
    impact_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    sentiment: Literal["POSITIVE", "NEUTRAL", "NEGATIVE"]
    category: NewsCategory | None = None


class NewsItemCreate(BaseModel):
    raw_news_event_id: int | None = None
    asset_id: int
    title: str = Field(max_length=500)
    url: str = Field(max_length=2048)
    source: str = Field(max_length=100)
    published_at: datetime | None = None
    summary: str | None = None
    category: str | None = Field(default=None, max_length=30)
    sentiment: str | None = Field(default=None, max_length=20)
    impact_level: str | None = Field(default=None, max_length=20)
    trust_level: str | None = Field(default=None, max_length=20)
    content_hash: str | None = Field(default=None, max_length=64)
    positive_factors: str | None = None
    negative_factors: str | None = None


class NewsItemResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    raw_news_event_id: int | None
    asset_id: int
    title: str
    url: str
    source: str
    published_at: UtcDatetime | None
    summary: str | None
    category: str | None
    sentiment: str | None
    impact_level: str | None
    trust_level: str | None
    content_hash: str | None
    positive_factors: str | None
    negative_factors: str | None
    created_at: UtcDatetime


class NewsItemProjection(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    title: str
    url: str
    source: str
    published_at: UtcDatetime | None
    summary: str | None
    category: str | None
    impact_level: str | None
    sentiment: str | None


class DisclosureItemProjection(BaseModel):
    title: str
    url: str
    source: str
    published_at: UtcDatetime | None
    category: str | None
    impact_level: str | None
    summary: str | None


class NewsDisclosureResponse(BaseModel):
    asset_id: int
    news: list[NewsItemProjection]
    disclosures: list[DisclosureItemProjection]
