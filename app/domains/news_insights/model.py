from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domains.news_insights.types import EventStatus, ProcessingStatus


def _score_constraint(table_name: str, column_name: str) -> CheckConstraint:
    return CheckConstraint(
        f"{column_name} >= 0.0 AND {column_name} <= 1.0",
        name=f"ck_{table_name}_{column_name}_range",
    )


class SourceDocument(Base):
    __tablename__ = "source_documents"
    __table_args__ = (
        _score_constraint("source_documents", "source_reliability"),
        Index(
            "ix_source_documents_document_type_published_at",
            "document_type",
            "published_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    raw_content: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(String(10), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    source_reliability: Mapped[float] = mapped_column(Float, nullable=False)
    processing_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ProcessingStatus.PENDING.value,
        server_default=ProcessingStatus.PENDING.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ExtractedEvent(Base):
    __tablename__ = "extracted_events"
    __table_args__ = (
        _score_constraint("extracted_events", "importance_score"),
        _score_constraint("extracted_events", "sentiment_score"),
        _score_constraint("extracted_events", "confidence_score"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    importance_score: Mapped[float] = mapped_column(Float, nullable=False)
    sentiment_direction: Mapped[str] = mapped_column(String(20), nullable=False)
    sentiment_score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    primary_symbol: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sector_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    event_fingerprint: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=EventStatus.ACTIVE.value,
        server_default=EventStatus.ACTIVE.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class EventEvidence(Base):
    __tablename__ = "event_evidence"
    __table_args__ = (
        _score_constraint("event_evidence", "relevance_score"),
        Index(
            "ix_event_evidence_event_id_evidence_role",
            "event_id",
            "evidence_role",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("extracted_events.id"), nullable=False
    )
    document_id: Mapped[int] = mapped_column(
        ForeignKey("source_documents.id"), nullable=False
    )
    relevance_score: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_role: Mapped[str] = mapped_column(String(20), nullable=False)
    extracted_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TopicCluster(Base):
    __tablename__ = "topic_clusters"
    __table_args__ = (
        _score_constraint("topic_clusters", "momentum_score"),
        _score_constraint("topic_clusters", "sentiment_score"),
        _score_constraint("topic_clusters", "impact_score"),
        _score_constraint("topic_clusters", "confidence_score"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(30), nullable=True)
    mention_count: Mapped[int] = mapped_column(Integer, nullable=False)
    momentum_score: Mapped[float] = mapped_column(Float, nullable=False)
    sentiment_score: Mapped[float] = mapped_column(Float, nullable=False)
    impact_score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    lifecycle_status: Mapped[str] = mapped_column(String(20), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TopicKeyword(Base):
    __tablename__ = "topic_keywords"
    __table_args__ = (
        _score_constraint("topic_keywords", "weight"),
        _score_constraint("topic_keywords", "sentiment_score"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topic_clusters.id"), nullable=False, index=True
    )
    keyword: Mapped[str] = mapped_column(String(255), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    sentiment_score: Mapped[float] = mapped_column(Float, nullable=False)
    category: Mapped[str | None] = mapped_column(String(30), nullable=True)
    mention_count: Mapped[int] = mapped_column(Integer, nullable=False)


class KeywordRelation(Base):
    __tablename__ = "keyword_relations"
    __table_args__ = (_score_constraint("keyword_relations", "strength"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topic_clusters.id"), nullable=False
    )
    source_keyword: Mapped[str] = mapped_column(String(255), nullable=False)
    target_keyword: Mapped[str] = mapped_column(String(255), nullable=False)
    strength: Mapped[float] = mapped_column(Float, nullable=False)
    cooccurrence_count: Mapped[int] = mapped_column(Integer, nullable=False)


class TopicInsight(Base):
    __tablename__ = "topic_insights"
    __table_args__ = (
        _score_constraint("topic_insights", "impact_score"),
        _score_constraint("topic_insights", "confidence_score"),
        UniqueConstraint("topic_id", "version", name="uq_topic_insights_topic_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topic_clusters.id"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    executive_summary: Mapped[str] = mapped_column(Text, nullable=False)
    why_it_matters: Mapped[str] = mapped_column(Text, nullable=False)
    key_evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    risk_points: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    counter_arguments: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    impact_score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class InvestorFlow(Base):
    __tablename__ = "investor_flows"
    __table_args__ = (
        Index(
            "ix_investor_flows_topic_id_investor_type",
            "topic_id",
            "investor_type",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market: Mapped[str | None] = mapped_column(String(30), nullable=True)
    topic_id: Mapped[int | None] = mapped_column(
        ForeignKey("topic_clusters.id"), nullable=True
    )
    investor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    net_value: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    window: Mapped[str] = mapped_column(String(30), nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TopicSymbolSensitivity(Base):
    __tablename__ = "topic_symbol_sensitivity"
    __table_args__ = (
        _score_constraint("topic_symbol_sensitivity", "exposure_score"),
        UniqueConstraint(
            "topic_id",
            "symbol",
            name="uq_topic_symbol_sensitivity_topic_symbol",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topic_clusters.id"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    exposure_score: Mapped[float] = mapped_column(Float, nullable=False)
    impact_direction: Mapped[str] = mapped_column(String(20), nullable=False)
    relationship: Mapped[str] = mapped_column(String(30), nullable=False)
    valuation_burden: Mapped[str | None] = mapped_column(String(20), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MarketEvent(Base):
    __tablename__ = "market_events"
    __table_args__ = (
        _score_constraint("market_events", "importance_score"),
        Index("ix_market_events_scheduled_at", "scheduled_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    event_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(20), nullable=True)
    market: Mapped[str | None] = mapped_column(String(30), nullable=True)
    importance_score: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MarketEventTopic(Base):
    __tablename__ = "market_event_topics"
    __table_args__ = (
        UniqueConstraint(
            "market_event_id",
            "topic_id",
            name="uq_market_event_topics_event_topic",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market_event_id: Mapped[int] = mapped_column(
        ForeignKey("market_events.id"), nullable=False
    )
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topic_clusters.id"), nullable=False
    )


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    processed_documents: Mapped[int] = mapped_column(Integer, nullable=False)
    extracted_events: Mapped[int] = mapped_column(Integer, nullable=False)
    active_topics: Mapped[int] = mapped_column(Integer, nullable=False)
    analysis_version: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AgentRunStage(Base):
    __tablename__ = "agent_run_stages"
    __table_args__ = (
        UniqueConstraint(
            "agent_run_id",
            "stage",
            name="uq_agent_run_stages_run_stage",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_run_id: Mapped[int] = mapped_column(
        ForeignKey("agent_runs.id"), nullable=False
    )
    stage: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    delayed: Mapped[bool] = mapped_column(Boolean, nullable=False)


class FundFlowOutlook(Base):
    __tablename__ = "fund_flow_outlooks"
    __table_args__ = (
        _score_constraint("fund_flow_outlooks", "confidence"),
        Index(
            "ix_fund_flow_outlooks_analysis_version_sector",
            "analysis_version",
            "sector",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sector: Mapped[str] = mapped_column(String(100), nullable=False)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    likelihood: Mapped[str] = mapped_column(String(20), nullable=False)
    estimated_flow_low: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 4), nullable=True
    )
    estimated_flow_high: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 4), nullable=True
    )
    estimated_flow_currency: Mapped[str | None] = mapped_column(
        String(10), nullable=True
    )
    horizon: Mapped[str] = mapped_column(String(100), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    key_assumptions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    risk_factors: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    analysis_version: Mapped[str] = mapped_column(String(100), nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FundFlowScenario(Base):
    __tablename__ = "fund_flow_scenarios"
    __table_args__ = (
        _score_constraint("fund_flow_scenarios", "weight"),
        UniqueConstraint(
            "topic_id",
            "analysis_version",
            "scenario_kind",
            name="uq_fund_flow_scenarios_topic_version_kind",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topic_clusters.id"), nullable=False
    )
    scenario_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    expected_flow_direction: Mapped[str] = mapped_column(String(20), nullable=False)
    expected_net_flow_low: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 4), nullable=True
    )
    expected_net_flow_high: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 4), nullable=True
    )
    expected_net_flow_currency: Mapped[str | None] = mapped_column(
        String(10), nullable=True
    )
    key_assumptions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    benefiting_sectors: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    risk_sectors: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    related_symbols: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    invalidation_conditions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    analysis_version: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TopicExplanation(Base):
    __tablename__ = "topic_explanations"
    __table_args__ = (
        _score_constraint("topic_explanations", "data_coverage"),
        _score_constraint("topic_explanations", "confidence"),
        UniqueConstraint(
            "topic_id",
            "analysis_version",
            name="uq_topic_explanations_topic_version",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topic_clusters.id"), nullable=False
    )
    analysis_version: Mapped[str] = mapped_column(String(100), nullable=False)
    data_coverage: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    missing_data: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    limitations: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    already_priced_in: Mapped[bool] = mapped_column(Boolean, nullable=False)
    already_priced_in_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ExplanationFactor(Base):
    __tablename__ = "explanation_factors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic_explanation_id: Mapped[int] = mapped_column(
        ForeignKey("topic_explanations.id"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    contribution_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        _score_constraint("explanation_factors", "contribution_ratio"),
    )
