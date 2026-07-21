from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.pagination import decode_datetime_cursor, encode_datetime_cursor
from app.domains.news_insights.briefing import build_briefing
from app.domains.news_insights.repository import (
    HIGH_IMPORTANCE_MIN,
    MEDIUM_IMPORTANCE_MIN,
    EventRecord,
    NewsInsightsRepository,
    SummaryCounts,
)
from app.domains.news_insights.schema import (
    EventImportance,
    EventListItem,
    EventSentiment,
    EventSource,
    EventsQuery,
    OverviewQuery,
    OverviewResponse,
    OverviewSummary,
    SummaryMetric,
)
from app.domains.news_insights.types import (
    DocumentType,
    EventType,
    ImportanceLevel,
    SentimentDirection,
)


@dataclass(frozen=True)
class EventsResult:
    items: list[EventListItem]
    has_more: bool
    next_cursor: str | None


class NewsInsightsService:
    def __init__(self, db: Session) -> None:
        self.repository = NewsInsightsRepository(db)

    def get_overview(
        self,
        query: OverviewQuery,
        *,
        as_of: datetime | None = None,
    ) -> OverviewResponse:
        generated_at = as_of or datetime.now(UTC)
        current, previous = self.repository.aggregate_summary_with_change(
            as_of=generated_at,
            window=self._parse_window(query.window),
        )
        briefing = build_briefing(
            self.repository.briefing_candidates(),
            existing_event_ids=self.repository.active_event_ids(),
            generated_at=generated_at,
        )
        return OverviewResponse(
            as_of=generated_at,
            summary=self._summary(current, previous),
            briefing=briefing,
        )

    def list_events(self, query: EventsQuery) -> EventsResult:
        cursor = (
            decode_datetime_cursor(query.cursor) if query.cursor is not None else None
        )
        page = self.repository.list_events(query, cursor)
        items = [self._event_item(record) for record in page.records]
        next_cursor = None
        if page.has_more and page.records:
            last_event = page.records[-1].event
            next_cursor = encode_datetime_cursor(
                last_event.detected_at,
                last_event.id,
            )
        return EventsResult(
            items=items,
            has_more=page.has_more,
            next_cursor=next_cursor,
        )

    @staticmethod
    def _parse_window(window: str) -> timedelta:
        value = int(window[:-1])
        return timedelta(hours=value) if window.endswith("h") else timedelta(days=value)

    @staticmethod
    def _metric(current: int, previous: int) -> SummaryMetric:
        return SummaryMetric(count=current, change=current - previous)

    @classmethod
    def _summary(
        cls,
        current: SummaryCounts,
        previous: SummaryCounts,
    ) -> OverviewSummary:
        return OverviewSummary(
            high_importance_events=cls._metric(
                current.high_importance_events,
                previous.high_importance_events,
            ),
            sentiment_shifts=cls._metric(
                current.sentiment_shifts,
                previous.sentiment_shifts,
            ),
            active_topic_clusters=cls._metric(
                current.active_topic_clusters,
                previous.active_topic_clusters,
            ),
            fund_flow_signals=cls._metric(
                current.fund_flow_signals,
                previous.fund_flow_signals,
            ),
        )

    @staticmethod
    def _importance_level(score: float) -> ImportanceLevel:
        if score >= HIGH_IMPORTANCE_MIN:
            return ImportanceLevel.HIGH
        if score >= MEDIUM_IMPORTANCE_MIN:
            return ImportanceLevel.MEDIUM
        return ImportanceLevel.LOW

    @classmethod
    def _event_item(cls, record: EventRecord) -> EventListItem:
        event = record.event
        document = record.document
        return EventListItem(
            id=event.id,
            event_type=EventType(event.event_type),
            document_type=(
                DocumentType(document.document_type) if document is not None else None
            ),
            symbol=event.primary_symbol,
            title=event.title,
            summary=event.summary,
            importance=EventImportance(
                level=cls._importance_level(event.importance_score),
                score=event.importance_score,
            ),
            sentiment=EventSentiment(
                direction=SentimentDirection(event.sentiment_direction),
                score=event.sentiment_score,
            ),
            source=(
                EventSource(
                    name=document.source_name,
                    reliability=document.source_reliability,
                )
                if document is not None
                else None
            ),
            published_at=(
                document.published_at
                if document is not None
                else event.occurred_at or event.detected_at
            ),
            evidence_count=record.evidence_count,
            topic_ids=list(record.topic_ids),
        )
