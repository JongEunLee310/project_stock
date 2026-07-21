from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.core.pagination import DateTimeCursor
from app.domains.news_insights.briefing import BriefingCandidate
from app.domains.news_insights.model import (
    EventEvidence,
    ExtractedEvent,
    KeywordRelation,
    SourceDocument,
    TopicCluster,
    TopicInsight,
    TopicKeyword,
)
from app.domains.news_insights.schema import EventsQuery, TopicEvidenceQuery
from app.domains.news_insights.types import (
    EventStatus,
    EvidenceRole,
    ImportanceLevel,
    LifecycleStatus,
    SentimentDirection,
)


HIGH_IMPORTANCE_MIN = 0.8
MEDIUM_IMPORTANCE_MIN = 0.5


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
class EvidencePage:
    records: tuple[EvidenceRecord, ...]
    has_more: bool


@dataclass(frozen=True)
class TopicTrendRecords:
    events: tuple[ExtractedEvent, ...]
    evidence: tuple[EvidenceRecord, ...]


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
