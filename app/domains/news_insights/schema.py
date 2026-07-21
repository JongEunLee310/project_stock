from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.core.schema import UtcDatetime
from app.domains.news_insights.types import (
    DocumentType,
    EvidenceRole,
    EventType,
    ImportanceLevel,
    LifecycleStatus,
    SentimentDirection,
    SymbolRelationship,
    TopicCategory,
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


class TopicMapQuery(BaseModel):
    window: str = Field(default="7d", pattern=r"^[1-9]\d*[hd]$")
    market: str | None = None
    limit: int = Field(default=20, ge=1, le=100)


class TopicTrendQuery(BaseModel):
    window: str = Field(default="7d", pattern=r"^[1-9]\d*[hd]$")
    interval: str = Field(default="1d", pattern=r"^[1-9]\d*[hd]$")


class TopicEvidenceQuery(BaseModel):
    types: list[DocumentType] = Field(default_factory=list)
    direction: SentimentDirection | None = None
    cursor: str | None = None
    limit: int = Field(default=20, ge=1, le=100)


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


class EventDetailImportance(EventImportance):
    explanation: str


class EventAffectedSymbol(BaseModel):
    symbol: str
    direction: SentimentDirection
    exposure_score: float = Field(ge=0.0, le=1.0)
    reason: str


class EventDetailEvidence(BaseModel):
    document_id: int
    document_type: DocumentType
    source: str
    title: str
    published_at: UtcDatetime
    evidence_role: EvidenceRole


class EventRelatedTopic(BaseModel):
    topic_id: int
    title: str


class EventDetailResponse(BaseModel):
    event_type: EventType
    title: str
    summary: str
    importance: EventDetailImportance
    sentiment: EventSentiment
    affected_symbols: list[EventAffectedSymbol]
    evidence: list[EventDetailEvidence]
    related_topics: list[EventRelatedTopic]


class TopicMapNode(BaseModel):
    id: str
    label: str
    type: Literal["TOPIC", "KEYWORD"]
    mention_count: int = Field(ge=0)
    momentum_score: float = Field(ge=0.0, le=1.0)
    sentiment_score: float = Field(ge=0.0, le=1.0)
    category: TopicCategory | None


class TopicMapEdge(BaseModel):
    source: str
    target: str
    strength: float = Field(ge=0.0, le=1.0)
    cooccurrence_count: int = Field(ge=0)


class TopicMapResponse(BaseModel):
    nodes: list[TopicMapNode]
    edges: list[TopicMapEdge]


class TopicScores(BaseModel):
    impact: float = Field(ge=0.0, le=1.0)
    sentiment: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    momentum: float = Field(ge=0.0, le=1.0)


class AffectedSymbol(BaseModel):
    symbol: str
    exposure_score: float = Field(ge=0.0, le=1.0)
    impact_direction: SentimentDirection
    relationship: SymbolRelationship


class TopicInsightResponse(BaseModel):
    summary: str
    why_it_matters: str
    key_evidence: list[dict[str, Any]]
    risk_points: list[str]
    counter_arguments: list[str]


class TopicDetailResponse(BaseModel):
    title: str
    tags: list[str]
    lifecycle: LifecycleStatus
    scores: TopicScores
    affected_symbols: list[AffectedSymbol]
    insight: TopicInsightResponse
    version: int = Field(ge=1)
    updated_at: UtcDatetime


class TopicTrendPoint(BaseModel):
    timestamp: UtcDatetime
    mention_count: int = Field(ge=0)
    sentiment_score: float = Field(ge=0.0, le=1.0)
    impact_score: float = Field(ge=0.0, le=1.0)


class TopicTrendMarker(BaseModel):
    timestamp: UtcDatetime
    label: str
    event_id: int


class TopicSourceDistribution(BaseModel):
    source_type: DocumentType
    count: int = Field(ge=0)
    share: float = Field(ge=0.0, le=1.0)


class TopicTrendResponse(BaseModel):
    points: list[TopicTrendPoint]
    markers: list[TopicTrendMarker]
    source_distribution: list[TopicSourceDistribution]


class TopicEvidenceItem(BaseModel):
    event_id: int
    document_id: int
    evidence_role: EvidenceRole
    document_type: DocumentType
    symbol: str | None
    title: str
    summary: str
    direction: SentimentDirection
    relevance_score: float = Field(ge=0.0, le=1.0)
    source: str
    published_at: UtcDatetime
