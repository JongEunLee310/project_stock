from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.core.schema import UtcDatetime
from app.domains.news_insights.types import (
    DocumentType,
    EventType,
    ImportanceLevel,
    SentimentDirection,
)


class OverviewQuery(BaseModel):
    market: str | None = None
    window: str = Field(default="24h", pattern=r"^[1-9]\d*[hd]$")
    portfolio_id: int | None = Field(default=None, ge=1)


class EventsQuery(BaseModel):
    types: list[EventType] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)
    importance: list[ImportanceLevel] = Field(default_factory=list)
    sentiment: list[SentimentDirection] = Field(default_factory=list)
    market: str | None = None
    from_: datetime | None = None
    to: datetime | None = None
    cursor: str | None = None
    limit: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def validate_time_range(self) -> "EventsQuery":
        if self.from_ is not None and self.to is not None and self.from_ > self.to:
            raise ValueError("from must be earlier than or equal to to")
        return self


class SummaryMetric(BaseModel):
    count: int = Field(ge=0)
    change: int


class OverviewSummary(BaseModel):
    high_importance_events: SummaryMetric
    sentiment_shifts: SummaryMetric
    active_topic_clusters: SummaryMetric
    fund_flow_signals: SummaryMetric


class BriefingHighlight(BaseModel):
    text: str
    topic_id: int
    evidence_count: int = Field(ge=0)
    evidence_event_ids: list[int]


class BriefingResponse(BaseModel):
    summary: str
    highlights: list[BriefingHighlight]
    generated_at: UtcDatetime


class OverviewResponse(BaseModel):
    as_of: UtcDatetime
    summary: OverviewSummary
    briefing: BriefingResponse


class EventImportance(BaseModel):
    level: ImportanceLevel
    score: float = Field(ge=0.0, le=1.0)


class EventSentiment(BaseModel):
    direction: SentimentDirection
    score: float = Field(ge=0.0, le=1.0)


class EventSource(BaseModel):
    name: str
    reliability: float = Field(ge=0.0, le=1.0)


class EventListItem(BaseModel):
    id: int
    event_type: EventType
    document_type: DocumentType | None
    symbol: str | None
    title: str
    summary: str
    importance: EventImportance
    sentiment: EventSentiment
    source: EventSource | None
    published_at: UtcDatetime
    evidence_count: int = Field(ge=0)
    topic_ids: list[int]
