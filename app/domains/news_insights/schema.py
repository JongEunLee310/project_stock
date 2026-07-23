from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, field_serializer, field_validator, model_validator

from app.core.schema import UtcDatetime
from app.domains.news_insights.types import (
    AgentRunStatus,
    AgentStage,
    DocumentType,
    EvidenceRole,
    EventType,
    FlowLikelihood,
    FundFlowDirection,
    ImportanceLevel,
    FlowDirection,
    InvestorType,
    LifecycleStatus,
    MarketEventKind,
    ScenarioKind,
    SentimentDirection,
    SymbolRelationship,
    TopicCategory,
    ValuationBurden,
)
from app.domains.signals.types import SignalType


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


class InvestorFlowsQuery(BaseModel):
    market: str = Field(min_length=1)
    window: str = Field(pattern=r"^[1-9]\d*[hd]$")
    topic_id: int | None = Field(default=None, ge=1)

    @field_validator("market")
    @classmethod
    def normalize_market(cls, value: str) -> str:
        return value.strip().upper()


class CalendarQuery(BaseModel):
    window: str = Field(pattern=r"^[1-9]\d*[hd]$")
    market: str = Field(min_length=1)
    topic_id: int | None = Field(default=None, ge=1)

    @field_validator("market")
    @classmethod
    def normalize_market(cls, value: str) -> str:
        return value.strip().upper()


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


class InvestorFlowItem(BaseModel):
    investor_type: InvestorType
    net_value: Decimal
    direction: FlowDirection
    change: float

    @field_serializer("net_value", when_used="json")
    def serialize_decimal(self, value: Decimal) -> str:
        return format(value, "f")


class NarrativeAlignment(BaseModel):
    aligned: bool
    note: str


class InvestorFlowAvailability(BaseModel):
    available: bool
    fallback: str | None


class InvestorFlowsResponse(BaseModel):
    as_of: UtcDatetime
    aggregation_windows: list[str] | None
    by_investor_type: list[InvestorFlowItem]
    narrative_alignment: NarrativeAlignment
    availability: InvestorFlowAvailability


class CalendarItem(BaseModel):
    scheduled_at: UtcDatetime
    event_kind: MarketEventKind
    title: str
    symbol: str | None
    market: str | None
    importance: float = Field(ge=0.0, le=1.0)
    related_topic_ids: list[int]


class AgentRunStageItem(BaseModel):
    name: AgentStage
    status: AgentRunStatus
    delayed: bool


class AgentRunsResponse(BaseModel):
    last_processed_at: UtcDatetime
    processed_documents: int = Field(ge=0)
    extracted_events: int = Field(ge=0)
    active_topics: int = Field(ge=0)
    collected_sources: int = Field(ge=0)
    average_run_duration_seconds: int | None
    stages: list[AgentRunStageItem]
    analysis_version: str
    has_delay: bool


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


class TopicSymbolSensitivityItem(BaseModel):
    symbol: str
    exposure_score: float = Field(ge=0.0, le=1.0)
    impact_direction: SentimentDirection
    relationship: SymbolRelationship
    valuation_burden: ValuationBurden | None
    portfolio_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    current_signal: SignalType | None = None


class TopicGraphNode(BaseModel):
    id: str
    label: str
    type: Literal["KEYWORD"]
    mention_count: int = Field(ge=0)
    sentiment_score: float = Field(ge=0.0, le=1.0)
    related_event_ids: list[int]
    related_symbols: list[str]


class TopicGraphEdge(BaseModel):
    source: str
    target: str
    strength: float = Field(ge=0.0, le=1.0)
    cooccurrence_count: int = Field(ge=0)


class TopicGraphResponse(BaseModel):
    nodes: list[TopicGraphNode]
    edges: list[TopicGraphEdge]


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


class FundFlowRange(BaseModel):
    low: Decimal
    high: Decimal
    currency: str

    @model_validator(mode="after")
    def validate_bounds(self) -> "FundFlowRange":
        if self.low > self.high:
            raise ValueError("low must be less than or equal to high")
        return self

    @field_serializer("low", "high", when_used="json")
    def serialize_decimal(self, value: Decimal) -> str:
        return format(value, "f")


class FundFlowOutlookItem(BaseModel):
    sector: str
    direction: FundFlowDirection
    likelihood: FlowLikelihood
    estimated_flow: FundFlowRange | None
    horizon: str
    confidence: float = Field(ge=0.0, le=1.0)
    key_assumptions: list[str]
    risk_factors: list[str]


class FundFlowOutlookResponse(BaseModel):
    as_of: UtcDatetime
    analysis_version: str
    items: list[FundFlowOutlookItem]


class FundFlowScenarioItem(BaseModel):
    scenario_kind: ScenarioKind
    weight: float = Field(ge=0.0, le=1.0)
    expected_flow_direction: FundFlowDirection
    expected_net_flow: FundFlowRange | None
    key_assumptions: list[str]
    benefiting_sectors: list[str]
    risk_sectors: list[str]
    related_symbols: list[str]
    invalidation_conditions: list[str]


class FundFlowScenariosResponse(BaseModel):
    topic_id: int
    analysis_version: str
    as_of: UtcDatetime
    scenarios: list[FundFlowScenarioItem]


class ExplanationFactorItem(BaseModel):
    label: str
    contribution_ratio: float = Field(ge=0.0, le=1.0)


class ExplanationMeta(BaseModel):
    analysis_version: str
    data_coverage: float = Field(ge=0.0, le=1.0)
    last_updated: UtcDatetime
    missing_data: list[str]
    counter_argument_count: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)
    limitations: list[str]


class AlreadyPricedIn(BaseModel):
    likely: bool
    note: str | None


class ContradictingEvidenceItem(BaseModel):
    event_id: int
    document_id: int
    title: str
    source: str
    published_at: UtcDatetime


class CounterView(BaseModel):
    counter_arguments: list[str]
    invalidation_conditions: list[str]
    already_priced_in: AlreadyPricedIn
    contradicting_evidence: list[ContradictingEvidenceItem]


class TopicExplanationResponse(BaseModel):
    factors: list[ExplanationFactorItem]
    meta: ExplanationMeta
    counter_view: CounterView
