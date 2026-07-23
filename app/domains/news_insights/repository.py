from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.core.pagination import DateTimeCursor
from app.domains.news_insights.briefing import BriefingCandidate
from app.domains.news_insights.model import (
    AgentRun,
    AgentRunStage,
    EventEvidence,
    ExplanationFactor,
    ExtractedEvent,
    FundFlowOutlook,
    FundFlowScenario,
    InvestorFlow,
    KeywordRelation,
    MarketEvent,
    MarketEventTopic,
    SourceDocument,
    TopicCluster,
    TopicExplanation,
    TopicInsight,
    TopicKeyword,
    TopicSymbolSensitivity,
)
from app.domains.news_insights.schema import (
    CalendarQuery,
    EventsQuery,
    InvestorFlowsQuery,
    TopicEvidenceQuery,
)
from app.domains.news_insights.types import (
    EventStatus,
    EvidenceRole,
    ImportanceLevel,
    LifecycleStatus,
    SentimentDirection,
)


HIGH_IMPORTANCE_MIN = 0.8
MEDIUM_IMPORTANCE_MIN = 0.5
AGENT_RUN_DURATION_SAMPLE_LIMIT = 20


@dataclass(frozen=True)
class EventRecord:
    event: ExtractedEvent
    document: SourceDocument | None
    evidence_count: int
    topic_ids: tuple[int, ...]


@dataclass(frozen=True)
class EventPage:
    records: tuple[EventRecord, ...]
    has_more: bool


@dataclass(frozen=True)
class SummaryCounts:
    high_importance_events: int
    sentiment_shifts: int
    active_topic_clusters: int
    fund_flow_signals: int = 0


@dataclass(frozen=True)
class TopicMapRecords:
    topics: tuple[TopicCluster, ...]
    keywords: tuple[TopicKeyword, ...]
    relations: tuple[KeywordRelation, ...]


@dataclass(frozen=True)
class TopicGraphRecords:
    keywords: tuple[TopicKeyword, ...]
    relations: tuple[KeywordRelation, ...]
    related_event_ids: tuple[int, ...]
    related_symbols: tuple[str, ...]


@dataclass(frozen=True)
class AffectedEventRecord:
    event: ExtractedEvent
    exposure_score: float


@dataclass(frozen=True)
class TopicDetailRecords:
    topic: TopicCluster
    insight: TopicInsight
    keywords: tuple[TopicKeyword, ...]
    affected_events: tuple[AffectedEventRecord, ...]


@dataclass(frozen=True)
class EvidenceRecord:
    evidence: EventEvidence
    event: ExtractedEvent
    document: SourceDocument


@dataclass(frozen=True)
class EventDetailRecords:
    event: ExtractedEvent
    evidence: tuple[EvidenceRecord, ...]
    topics: tuple[TopicCluster, ...]


@dataclass(frozen=True)
class EvidencePage:
    records: tuple[EvidenceRecord, ...]
    has_more: bool


@dataclass(frozen=True)
class TopicTrendRecords:
    events: tuple[ExtractedEvent, ...]
    evidence: tuple[EvidenceRecord, ...]


@dataclass(frozen=True)
class InvestorFlowAggregate:
    investor_type: str
    net_value: Decimal
    previous_net_value: Decimal | None


@dataclass(frozen=True)
class InvestorFlowRecords:
    as_of: datetime | None
    aggregation_windows: tuple[str, ...]
    aggregates: tuple[InvestorFlowAggregate, ...]
    narrative_sentiment_score: float | None
    fallback_source_kinds: tuple[str, ...]


@dataclass(frozen=True)
class CalendarRecord:
    event: MarketEvent
    related_topic_ids: tuple[int, ...]


@dataclass(frozen=True)
class AgentRunRecords:
    run: AgentRun
    stages: tuple[AgentRunStage, ...]
    collected_sources: int
    average_run_duration_seconds: int | None


@dataclass(frozen=True)
class FundFlowOutlookRecords:
    analysis_version: str
    as_of: datetime
    items: tuple[FundFlowOutlook, ...]


@dataclass(frozen=True)
class TopicScenarioRecords:
    analysis_version: str
    as_of: datetime
    scenarios: tuple[FundFlowScenario, ...]


@dataclass(frozen=True)
class TopicExplanationRecords:
    explanation: TopicExplanation
    factors: tuple[ExplanationFactor, ...]
    counter_arguments: tuple[str, ...]
    invalidation_conditions: tuple[str, ...]
    contradicting_evidence: tuple[EvidenceRecord, ...]


class NewsInsightsRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_events(
        self,
        query: EventsQuery,
        cursor: DateTimeCursor | None,
    ) -> EventPage:
        stmt = (
            select(ExtractedEvent)
            .where(*self._event_conditions(query, cursor))
            .order_by(ExtractedEvent.detected_at.desc(), ExtractedEvent.id.desc())
            .limit(query.limit + 1)
        )
        fetched_events = list(self.db.scalars(stmt).all())
        has_more = len(fetched_events) > query.limit
        events = fetched_events[: query.limit]
        event_ids = [event.id for event in events]
        documents, evidence_counts = self._documents_by_event(event_ids)
        topic_ids = self._topic_ids_by_event(event_ids)
        return EventPage(
            records=tuple(
                EventRecord(
                    event=event,
                    document=documents.get(event.id),
                    evidence_count=evidence_counts.get(event.id, 0),
                    topic_ids=tuple(topic_ids.get(event.id, ())),
                )
                for event in events
            ),
            has_more=has_more,
        )

    def list_calendar_events(
        self,
        query: CalendarQuery,
        *,
        start: datetime,
        end: datetime,
    ) -> tuple[CalendarRecord, ...]:
        conditions = [
            MarketEvent.scheduled_at >= start,
            MarketEvent.scheduled_at <= end,
            MarketEvent.market == query.market,
        ]
        stmt = select(MarketEvent)
        if query.topic_id is not None:
            stmt = stmt.join(
                MarketEventTopic,
                MarketEventTopic.market_event_id == MarketEvent.id,
            )
            conditions.append(MarketEventTopic.topic_id == query.topic_id)
        events = tuple(
            self.db.scalars(
                stmt.where(*conditions).order_by(
                    MarketEvent.scheduled_at,
                    MarketEvent.id,
                )
            ).all()
        )
        event_ids = [event.id for event in events]
        topic_ids_by_event: dict[int, list[int]] = {}
        if event_ids:
            for event_id, topic_id in self.db.execute(
                select(
                    MarketEventTopic.market_event_id,
                    MarketEventTopic.topic_id,
                )
                .where(MarketEventTopic.market_event_id.in_(event_ids))
                .order_by(
                    MarketEventTopic.market_event_id,
                    MarketEventTopic.topic_id,
                )
            ).all():
                topic_ids_by_event.setdefault(event_id, []).append(topic_id)
        return tuple(
            CalendarRecord(
                event=event,
                related_topic_ids=tuple(topic_ids_by_event.get(event.id, ())),
            )
            for event in events
        )

    def latest_agent_run_records(self, *, as_of: datetime) -> AgentRunRecords | None:
        run = self.db.scalars(
            select(AgentRun)
            .order_by(AgentRun.started_at.desc(), AgentRun.id.desc())
            .limit(1)
        ).first()
        if run is None:
            return None
        stages = tuple(
            self.db.scalars(
                select(AgentRunStage)
                .where(AgentRunStage.agent_run_id == run.id)
                .order_by(AgentRunStage.id)
            ).all()
        )
        interval_end = run.finished_at or as_of
        collected_sources = int(
            self.db.scalar(
                select(func.count(func.distinct(SourceDocument.source_name))).where(
                    SourceDocument.collected_at >= run.started_at,
                    SourceDocument.collected_at <= interval_end,
                )
            )
            or 0
        )
        return AgentRunRecords(
            run=run,
            stages=stages,
            collected_sources=collected_sources,
            average_run_duration_seconds=self._average_run_duration_seconds(),
        )

    def _average_run_duration_seconds(self) -> int | None:
        if self.db.get_bind().dialect.name == "sqlite":
            duration_seconds = (
                func.julianday(AgentRun.finished_at)
                - func.julianday(AgentRun.started_at)
            ) * 86400.0
        else:
            duration_seconds = func.extract(
                "epoch",
                AgentRun.finished_at - AgentRun.started_at,
            )
        recent_durations = (
            select(duration_seconds.label("duration_seconds"))
            .where(AgentRun.finished_at.is_not(None))
            .order_by(AgentRun.started_at.desc(), AgentRun.id.desc())
            .limit(AGENT_RUN_DURATION_SAMPLE_LIMIT)
            .subquery()
        )
        average_duration = self.db.scalar(
            select(func.round(func.avg(recent_durations.c.duration_seconds)))
        )
        return int(average_duration) if average_duration is not None else None

    def event_detail_records(self, event_id: int) -> EventDetailRecords | None:
        event = self.db.get(ExtractedEvent, event_id)
        if event is None:
            return None
        topic_ids = self._topic_ids_by_event([event_id]).get(event_id, [])
        topics = tuple(
            self.db.scalars(
                select(TopicCluster)
                .where(TopicCluster.id.in_(topic_ids))
                .order_by(TopicCluster.id)
            ).all()
        )
        return EventDetailRecords(
            event=event,
            evidence=self._evidence_records([event_id]),
            topics=topics,
        )

    def aggregate_summary(
        self,
        *,
        start: datetime,
        end: datetime,
    ) -> SummaryCounts:
        event_counts = self.db.execute(
            select(
                func.sum(
                    case(
                        (ExtractedEvent.importance_score >= HIGH_IMPORTANCE_MIN, 1),
                        else_=0,
                    )
                ),
                func.sum(
                    case(
                        (
                            ExtractedEvent.sentiment_direction
                            != SentimentDirection.NEUTRAL.value,
                            1,
                        ),
                        else_=0,
                    )
                ),
            ).where(
                ExtractedEvent.status == EventStatus.ACTIVE.value,
                ExtractedEvent.detected_at >= start,
                ExtractedEvent.detected_at < end,
            )
        ).one()
        active_topic_clusters = int(
            self.db.scalar(
                select(func.count(TopicCluster.id)).where(
                    TopicCluster.lifecycle_status.in_(
                        (
                            LifecycleStatus.EMERGING.value,
                            LifecycleStatus.RISING.value,
                            LifecycleStatus.ACTIVE.value,
                        )
                    ),
                    TopicCluster.last_activity_at >= start,
                    TopicCluster.last_activity_at < end,
                )
            )
            or 0
        )
        return SummaryCounts(
            high_importance_events=int(event_counts[0] or 0),
            sentiment_shifts=int(event_counts[1] or 0),
            active_topic_clusters=active_topic_clusters,
        )

    def aggregate_summary_with_change(
        self,
        *,
        as_of: datetime,
        window: timedelta,
    ) -> tuple[SummaryCounts, SummaryCounts]:
        current_start = as_of - window
        previous_start = current_start - window
        return (
            self.aggregate_summary(start=current_start, end=as_of),
            self.aggregate_summary(start=previous_start, end=current_start),
        )

    def active_event_ids(self) -> set[int]:
        return set(
            self.db.scalars(
                select(ExtractedEvent.id).where(
                    ExtractedEvent.status == EventStatus.ACTIVE.value
                )
            ).all()
        )

    def topic_map_records(
        self,
        *,
        start: datetime,
        limit: int,
    ) -> TopicMapRecords:
        topics = tuple(
            self.db.scalars(
                select(TopicCluster)
                .where(
                    TopicCluster.last_activity_at >= start,
                    TopicCluster.lifecycle_status != LifecycleStatus.ARCHIVED.value,
                )
                .order_by(
                    TopicCluster.momentum_score.desc(),
                    TopicCluster.mention_count.desc(),
                    TopicCluster.id,
                )
                .limit(limit)
            ).all()
        )
        topic_ids = [topic.id for topic in topics]
        if not topic_ids:
            return TopicMapRecords(topics=(), keywords=(), relations=())
        keywords = tuple(
            self.db.scalars(
                select(TopicKeyword)
                .where(TopicKeyword.topic_id.in_(topic_ids))
                .order_by(
                    TopicKeyword.topic_id,
                    TopicKeyword.weight.desc(),
                    TopicKeyword.id,
                )
            ).all()
        )
        relations = tuple(
            self.db.scalars(
                select(KeywordRelation)
                .where(KeywordRelation.topic_id.in_(topic_ids))
                .order_by(KeywordRelation.topic_id, KeywordRelation.id)
            ).all()
        )
        return TopicMapRecords(
            topics=topics,
            keywords=keywords,
            relations=relations,
        )

    def topic_exists(self, topic_id: int) -> bool:
        return self.db.get(TopicCluster, topic_id) is not None

    def latest_fund_flow_outlooks(self) -> FundFlowOutlookRecords | None:
        latest = self.db.scalars(
            select(FundFlowOutlook)
            .order_by(FundFlowOutlook.as_of.desc(), FundFlowOutlook.id.desc())
            .limit(1)
        ).first()
        if latest is None:
            return None
        items = tuple(
            self.db.scalars(
                select(FundFlowOutlook)
                .where(
                    FundFlowOutlook.analysis_version == latest.analysis_version
                )
                .order_by(FundFlowOutlook.sector, FundFlowOutlook.id)
            ).all()
        )
        return FundFlowOutlookRecords(
            analysis_version=latest.analysis_version,
            as_of=max(item.as_of for item in items),
            items=items,
        )

    def latest_topic_scenarios(self, topic_id: int) -> TopicScenarioRecords | None:
        latest = self.db.scalars(
            select(FundFlowScenario)
            .where(FundFlowScenario.topic_id == topic_id)
            .order_by(FundFlowScenario.created_at.desc(), FundFlowScenario.id.desc())
            .limit(1)
        ).first()
        if latest is None:
            return None
        scenarios = tuple(
            self.db.scalars(
                select(FundFlowScenario)
                .where(
                    FundFlowScenario.topic_id == topic_id,
                    FundFlowScenario.analysis_version == latest.analysis_version,
                )
                .order_by(FundFlowScenario.id)
            ).all()
        )
        return TopicScenarioRecords(
            analysis_version=latest.analysis_version,
            as_of=max(item.created_at for item in scenarios),
            scenarios=scenarios,
        )

    def latest_topic_explanation(
        self,
        topic_id: int,
    ) -> TopicExplanationRecords | None:
        explanation = self.db.scalars(
            select(TopicExplanation)
            .where(TopicExplanation.topic_id == topic_id)
            .order_by(
                TopicExplanation.last_updated.desc(),
                TopicExplanation.id.desc(),
            )
            .limit(1)
        ).first()
        if explanation is None:
            return None
        factors = tuple(
            self.db.scalars(
                select(ExplanationFactor)
                .where(
                    ExplanationFactor.topic_explanation_id == explanation.id
                )
                .order_by(
                    ExplanationFactor.display_order,
                    ExplanationFactor.id,
                )
            ).all()
        )
        insight = self.db.scalars(
            select(TopicInsight)
            .where(TopicInsight.topic_id == topic_id)
            .order_by(TopicInsight.version.desc(), TopicInsight.id.desc())
            .limit(1)
        ).first()
        counter_arguments = tuple(insight.counter_arguments) if insight else ()
        event_ids = self._topic_event_ids(topic_id)
        contradicting_evidence = tuple(
            record
            for record in self._evidence_records(event_ids)
            if record.evidence.evidence_role == EvidenceRole.CONTRADICTING.value
        )
        scenario_conditions = self.db.scalars(
            select(FundFlowScenario.invalidation_conditions)
            .where(
                FundFlowScenario.topic_id == topic_id,
                FundFlowScenario.analysis_version == explanation.analysis_version,
            )
            .order_by(FundFlowScenario.id)
        ).all()
        invalidation_conditions = tuple(
            dict.fromkeys(
                condition
                for conditions in scenario_conditions
                for condition in conditions
            )
        )
        return TopicExplanationRecords(
            explanation=explanation,
            factors=factors,
            counter_arguments=counter_arguments,
            invalidation_conditions=invalidation_conditions,
            contradicting_evidence=contradicting_evidence,
        )

    def list_topic_symbol_sensitivities(
        self,
        topic_id: int,
    ) -> tuple[TopicSymbolSensitivity, ...]:
        return tuple(
            self.db.scalars(
                select(TopicSymbolSensitivity)
                .where(TopicSymbolSensitivity.topic_id == topic_id)
                .order_by(
                    TopicSymbolSensitivity.exposure_score.desc(),
                    TopicSymbolSensitivity.symbol,
                )
            ).all()
        )

    def topic_graph_records(self, topic_id: int) -> TopicGraphRecords:
        keywords = tuple(
            self.db.scalars(
                select(TopicKeyword)
                .where(TopicKeyword.topic_id == topic_id)
                .order_by(TopicKeyword.weight.desc(), TopicKeyword.id)
            ).all()
        )
        relations = tuple(
            self.db.scalars(
                select(KeywordRelation)
                .where(KeywordRelation.topic_id == topic_id)
                .order_by(KeywordRelation.id)
            ).all()
        )
        related_event_ids = tuple(sorted(self._topic_event_ids(topic_id)))
        event_symbols = self.db.scalars(
            select(ExtractedEvent.primary_symbol)
            .where(
                ExtractedEvent.id.in_(related_event_ids),
                ExtractedEvent.primary_symbol.is_not(None),
            )
            .order_by(ExtractedEvent.primary_symbol)
        ).all()
        sensitivity_symbols = self.db.scalars(
            select(TopicSymbolSensitivity.symbol)
            .where(TopicSymbolSensitivity.topic_id == topic_id)
            .order_by(TopicSymbolSensitivity.symbol)
        ).all()
        return TopicGraphRecords(
            keywords=keywords,
            relations=relations,
            related_event_ids=related_event_ids,
            related_symbols=tuple(
                sorted(
                    {
                        symbol
                        for symbol in (*event_symbols, *sensitivity_symbols)
                        if symbol is not None
                    }
                )
            ),
        )

    def investor_flow_records(
        self,
        query: InvestorFlowsQuery,
        *,
        as_of: datetime,
        window: timedelta,
    ) -> InvestorFlowRecords:
        start = as_of - window
        conditions = [
            InvestorFlow.market == query.market,
            InvestorFlow.as_of >= start,
        ]
        if query.topic_id is not None:
            conditions.append(InvestorFlow.topic_id == query.topic_id)

        rows = self.db.execute(
            select(
                InvestorFlow.investor_type,
                InvestorFlow.as_of,
                InvestorFlow.source_kind,
                func.sum(InvestorFlow.net_value),
            )
            .where(*conditions)
            .group_by(
                InvestorFlow.investor_type,
                InvestorFlow.as_of,
                InvestorFlow.source_kind,
            )
            .order_by(
                InvestorFlow.investor_type,
                InvestorFlow.as_of.desc(),
            )
        ).all()
        values_by_type: dict[str, list[tuple[datetime, Decimal]]] = {}
        fallback_source_kinds: set[str] = set()
        for investor_type, as_of, source_kind, net_value in rows:
            if source_kind != "INVESTOR_TYPE":
                fallback_source_kinds.add(source_kind)
                continue
            values_by_type.setdefault(investor_type, []).append(
                (as_of, Decimal(net_value))
            )

        aggregates = tuple(
            InvestorFlowAggregate(
                investor_type=investor_type,
                net_value=values[0][1],
                previous_net_value=values[1][1] if len(values) > 1 else None,
            )
            for investor_type, values in sorted(values_by_type.items())
        )
        current_as_of = max(
            (values[0][0] for values in values_by_type.values()),
            default=None,
        )
        aggregation_windows = tuple(
            self.db.scalars(
                select(InvestorFlow.window)
                .where(
                    *conditions,
                    InvestorFlow.source_kind == "INVESTOR_TYPE",
                )
                .distinct()
                .order_by(InvestorFlow.window)
            ).all()
        )
        sentiment_score = self.db.scalar(
            select(func.avg(TopicCluster.sentiment_score))
            .join(InvestorFlow, InvestorFlow.topic_id == TopicCluster.id)
            .where(
                *conditions,
                InvestorFlow.source_kind == "INVESTOR_TYPE",
            )
        )
        return InvestorFlowRecords(
            as_of=current_as_of,
            aggregation_windows=aggregation_windows,
            aggregates=aggregates,
            narrative_sentiment_score=(
                float(sentiment_score) if sentiment_score is not None else None
            ),
            fallback_source_kinds=tuple(sorted(fallback_source_kinds)),
        )

    def topic_detail_records(self, topic_id: int) -> TopicDetailRecords | None:
        topic = self.db.get(TopicCluster, topic_id)
        if topic is None:
            return None
        insight = self.db.scalars(
            select(TopicInsight)
            .where(TopicInsight.topic_id == topic_id)
            .order_by(TopicInsight.version.desc(), TopicInsight.id.desc())
            .limit(1)
        ).first()
        if insight is None:
            return None
        keywords = tuple(
            self.db.scalars(
                select(TopicKeyword)
                .where(TopicKeyword.topic_id == topic_id)
                .order_by(TopicKeyword.weight.desc(), TopicKeyword.id)
            ).all()
        )
        event_ids = self._insight_event_ids(insight)
        events = tuple(
            self.db.scalars(
                select(ExtractedEvent)
                .where(
                    ExtractedEvent.id.in_(event_ids),
                    ExtractedEvent.status == EventStatus.ACTIVE.value,
                    ExtractedEvent.primary_symbol.is_not(None),
                )
                .order_by(ExtractedEvent.importance_score.desc(), ExtractedEvent.id)
            ).all()
        )
        relevance_by_event = self._max_relevance_by_event(event_ids)
        return TopicDetailRecords(
            topic=topic,
            insight=insight,
            keywords=keywords,
            affected_events=tuple(
                AffectedEventRecord(
                    event=event,
                    exposure_score=relevance_by_event.get(
                        event.id, event.importance_score
                    ),
                )
                for event in events
            ),
        )

    def topic_trend_records(
        self,
        topic_id: int,
        *,
        start: datetime,
        end: datetime,
    ) -> TopicTrendRecords:
        event_ids = self._topic_event_ids(topic_id)
        if not event_ids:
            return TopicTrendRecords(events=(), evidence=())
        events = tuple(
            self.db.scalars(
                select(ExtractedEvent)
                .where(
                    ExtractedEvent.id.in_(event_ids),
                    ExtractedEvent.status == EventStatus.ACTIVE.value,
                    ExtractedEvent.detected_at >= start,
                    ExtractedEvent.detected_at <= end,
                )
                .order_by(ExtractedEvent.detected_at, ExtractedEvent.id)
            ).all()
        )
        records = self._evidence_records([event.id for event in events])
        return TopicTrendRecords(events=events, evidence=records)

    def list_topic_evidence(
        self,
        topic_id: int,
        query: TopicEvidenceQuery,
        cursor: DateTimeCursor | None,
    ) -> EvidencePage:
        event_ids = self._topic_event_ids(topic_id)
        if not event_ids:
            return EvidencePage(records=(), has_more=False)
        conditions: list[Any] = [
            EventEvidence.event_id.in_(event_ids),
            ExtractedEvent.status == EventStatus.ACTIVE.value,
        ]
        if query.types:
            conditions.append(
                SourceDocument.document_type.in_([item.value for item in query.types])
            )
        if query.direction is not None:
            conditions.append(
                ExtractedEvent.sentiment_direction == query.direction.value
            )
        if cursor is not None:
            conditions.append(
                or_(
                    SourceDocument.published_at < cursor.timestamp,
                    and_(
                        SourceDocument.published_at == cursor.timestamp,
                        EventEvidence.id < cursor.row_id,
                    ),
                )
            )
        rows = self.db.execute(
            select(EventEvidence, ExtractedEvent, SourceDocument)
            .join(ExtractedEvent, ExtractedEvent.id == EventEvidence.event_id)
            .join(SourceDocument, SourceDocument.id == EventEvidence.document_id)
            .where(*conditions)
            .order_by(SourceDocument.published_at.desc(), EventEvidence.id.desc())
            .limit(query.limit + 1)
        ).all()
        has_more = len(rows) > query.limit
        return EvidencePage(
            records=tuple(
                EvidenceRecord(evidence=evidence, event=event, document=document)
                for evidence, event, document in rows[: query.limit]
            ),
            has_more=has_more,
        )

    def briefing_candidates(self) -> list[BriefingCandidate]:
        rows = self.db.execute(
            select(TopicInsight, TopicCluster)
            .join(TopicCluster, TopicCluster.id == TopicInsight.topic_id)
            .where(TopicCluster.lifecycle_status != LifecycleStatus.ARCHIVED.value)
            .order_by(
                TopicInsight.topic_id,
                TopicInsight.version.desc(),
                TopicInsight.id.desc(),
            )
        ).all()
        candidates: list[BriefingCandidate] = []
        seen_topic_ids: set[int] = set()
        for insight, topic in rows:
            if insight.topic_id in seen_topic_ids:
                continue
            seen_topic_ids.add(insight.topic_id)
            candidates.append(
                BriefingCandidate(
                    text=insight.executive_summary,
                    topic_id=topic.id,
                    evidence_event_ids=tuple(
                        event_id
                        for item in insight.key_evidence
                        if (event_id := self._evidence_event_id(item)) is not None
                    ),
                )
            )
        return candidates

    @staticmethod
    def _evidence_event_id(item: Any) -> int | None:
        if not isinstance(item, dict):
            return None
        event_id = item.get("event_id")
        return event_id if isinstance(event_id, int) else None

    @classmethod
    def _insight_event_ids(cls, insight: TopicInsight) -> list[int]:
        return list(
            dict.fromkeys(
                event_id
                for item in insight.key_evidence
                if (event_id := cls._evidence_event_id(item)) is not None
            )
        )

    def _topic_event_ids(self, topic_id: int) -> list[int]:
        event_ids: list[int] = []
        seen: set[int] = set()
        insights = self.db.scalars(
            select(TopicInsight)
            .where(TopicInsight.topic_id == topic_id)
            .order_by(TopicInsight.version, TopicInsight.id)
        ).all()
        for insight in insights:
            for event_id in self._insight_event_ids(insight):
                if event_id not in seen:
                    seen.add(event_id)
                    event_ids.append(event_id)
        return event_ids

    def _max_relevance_by_event(self, event_ids: list[int]) -> dict[int, float]:
        if not event_ids:
            return {}
        return {
            event_id: float(relevance)
            for event_id, relevance in self.db.execute(
                select(EventEvidence.event_id, func.max(EventEvidence.relevance_score))
                .where(EventEvidence.event_id.in_(event_ids))
                .group_by(EventEvidence.event_id)
            ).all()
        }

    def _evidence_records(self, event_ids: list[int]) -> tuple[EvidenceRecord, ...]:
        if not event_ids:
            return ()
        rows = self.db.execute(
            select(EventEvidence, ExtractedEvent, SourceDocument)
            .join(ExtractedEvent, ExtractedEvent.id == EventEvidence.event_id)
            .join(SourceDocument, SourceDocument.id == EventEvidence.document_id)
            .where(EventEvidence.event_id.in_(event_ids))
            .order_by(SourceDocument.published_at, EventEvidence.id)
        ).all()
        return tuple(
            EvidenceRecord(evidence=evidence, event=event, document=document)
            for evidence, event, document in rows
        )

    @staticmethod
    def _event_conditions(
        query: EventsQuery,
        cursor: DateTimeCursor | None,
    ) -> list[Any]:
        conditions: list[Any] = [
            ExtractedEvent.status == EventStatus.ACTIVE.value
        ]
        if query.types:
            conditions.append(
                ExtractedEvent.event_type.in_([item.value for item in query.types])
            )
        if query.symbols:
            conditions.append(ExtractedEvent.primary_symbol.in_(query.symbols))
        if query.sentiment:
            conditions.append(
                ExtractedEvent.sentiment_direction.in_(
                    [item.value for item in query.sentiment]
                )
            )
        if query.from_ is not None:
            conditions.append(ExtractedEvent.detected_at >= query.from_)
        if query.to is not None:
            conditions.append(ExtractedEvent.detected_at <= query.to)
        if query.importance:
            importance_conditions = []
            if ImportanceLevel.HIGH in query.importance:
                importance_conditions.append(
                    ExtractedEvent.importance_score >= HIGH_IMPORTANCE_MIN
                )
            if ImportanceLevel.MEDIUM in query.importance:
                importance_conditions.append(
                    and_(
                        ExtractedEvent.importance_score >= MEDIUM_IMPORTANCE_MIN,
                        ExtractedEvent.importance_score < HIGH_IMPORTANCE_MIN,
                    )
                )
            if ImportanceLevel.LOW in query.importance:
                importance_conditions.append(
                    ExtractedEvent.importance_score < MEDIUM_IMPORTANCE_MIN
                )
            conditions.append(or_(*importance_conditions))
        if cursor is not None:
            conditions.append(
                or_(
                    ExtractedEvent.detected_at < cursor.timestamp,
                    and_(
                        ExtractedEvent.detected_at == cursor.timestamp,
                        ExtractedEvent.id < cursor.row_id,
                    ),
                )
            )
        return conditions

    def _documents_by_event(
        self,
        event_ids: list[int],
    ) -> tuple[dict[int, SourceDocument], dict[int, int]]:
        if not event_ids:
            return {}, {}
        rows = self.db.execute(
            select(EventEvidence, SourceDocument)
            .join(SourceDocument, SourceDocument.id == EventEvidence.document_id)
            .where(EventEvidence.event_id.in_(event_ids))
            .order_by(
                EventEvidence.event_id,
                case(
                    (EventEvidence.evidence_role == EvidenceRole.PRIMARY.value, 0),
                    else_=1,
                ),
                EventEvidence.relevance_score.desc(),
                EventEvidence.id,
            )
        ).all()
        documents: dict[int, SourceDocument] = {}
        evidence_counts: dict[int, int] = {}
        for evidence, document in rows:
            evidence_counts[evidence.event_id] = (
                evidence_counts.get(evidence.event_id, 0) + 1
            )
            documents.setdefault(evidence.event_id, document)
        return documents, evidence_counts

    def _topic_ids_by_event(self, event_ids: list[int]) -> dict[int, list[int]]:
        topic_ids: dict[int, list[int]] = {event_id: [] for event_id in event_ids}
        if not event_ids:
            return topic_ids
        for insight in self.db.scalars(select(TopicInsight)).all():
            for item in insight.key_evidence:
                event_id = self._evidence_event_id(item)
                if (
                    event_id in topic_ids
                    and insight.topic_id not in topic_ids[event_id]
                ):
                    topic_ids[event_id].append(insight.topic_id)
        return topic_ids
