from abc import ABC, abstractmethod
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.domains.news_insights.clock import utcnow
from app.domains.news_insights.model import (
    ExtractedEvent,
    KeywordRelation,
    TopicCluster,
    TopicKeyword,
)
from app.domains.news_insights.types import (
    EventType,
    LifecycleStatus,
    TopicCategory,
)


NEUTRAL_SCORE = 0.5

_EVENT_TYPE_CATEGORIES = {
    EventType.EARNINGS_GUIDANCE: TopicCategory.EARNINGS,
    EventType.BUYBACK: TopicCategory.CAPITAL_POLICY,
    EventType.REGULATION: TopicCategory.REGULATION,
    EventType.SUPPLY_CONTRACT: TopicCategory.SUPPLY_CHAIN,
    EventType.MANAGEMENT_CHANGE: TopicCategory.MARKET_EVENT,
    EventType.ACCOUNTING_ISSUE: TopicCategory.EARNINGS,
    EventType.PRODUCTION_DISRUPTION: TopicCategory.SUPPLY_CHAIN,
    EventType.OTHER: TopicCategory.MARKET_EVENT,
}


@dataclass(frozen=True)
class TopicKeywordDraft:
    keyword: str
    weight: float
    sentiment_score: float
    category: TopicCategory | None
    mention_count: int


@dataclass(frozen=True)
class KeywordRelationDraft:
    source_keyword: str
    target_keyword: str
    strength: float
    cooccurrence_count: int


@dataclass(frozen=True)
class TopicClusterDraft:
    slug: str
    title: str
    summary: str | None
    category: TopicCategory
    mention_count: int
    momentum_score: float
    sentiment_score: float
    impact_score: float
    confidence_score: float
    keywords: tuple[TopicKeywordDraft, ...]
    relations: tuple[KeywordRelationDraft, ...]


class EventClusterer(ABC):
    @abstractmethod
    def cluster(
        self,
        events: list[ExtractedEvent],
    ) -> list[TopicClusterDraft]:
        """Cluster extracted events into deterministic topic drafts."""


class EventTypeClusterer(EventClusterer):
    def cluster(
        self,
        events: list[ExtractedEvent],
    ) -> list[TopicClusterDraft]:
        events_by_type: dict[EventType, list[ExtractedEvent]] = {}
        for event in events:
            event_type = EventType(event.event_type)
            events_by_type.setdefault(event_type, []).append(event)

        return [
            self._draft(event_type, grouped_events)
            for event_type, grouped_events in sorted(
                events_by_type.items(),
                key=lambda item: item[0].value,
            )
        ]

    def _draft(
        self,
        event_type: EventType,
        events: list[ExtractedEvent],
    ) -> TopicClusterDraft:
        mention_count = len(events)
        sentiment_score = (
            sum(event.sentiment_score for event in events) / mention_count
        )
        title = event_type.value.replace("_", " ").title()
        keyword = event_type.value.replace("_", " ").lower()
        return TopicClusterDraft(
            slug=event_type.value.replace("_", "-").lower(),
            title=title,
            summary=None,
            category=_EVENT_TYPE_CATEGORIES[event_type],
            mention_count=mention_count,
            momentum_score=NEUTRAL_SCORE,
            sentiment_score=sentiment_score,
            impact_score=NEUTRAL_SCORE,
            confidence_score=NEUTRAL_SCORE,
            keywords=(
                TopicKeywordDraft(
                    keyword=keyword,
                    weight=1.0,
                    sentiment_score=sentiment_score,
                    category=None,
                    mention_count=mention_count,
                ),
            ),
            relations=(),
        )


@dataclass(frozen=True)
class ClusteringResult:
    created_topic_count: int = 0
    updated_topic_count: int = 0
    created_keyword_count: int = 0
    created_relation_count: int = 0


def cluster_topics(
    db: Session,
    clusterer: EventClusterer,
) -> ClusteringResult:
    events = list(
        db.scalars(
            select(ExtractedEvent).order_by(ExtractedEvent.id)
        ).all()
    )
    drafts = clusterer.cluster(events)
    if not drafts:
        return ClusteringResult()

    processed_at = utcnow()
    existing_topics = {
        topic.slug: topic
        for topic in db.scalars(
            select(TopicCluster).where(
                TopicCluster.slug.in_(draft.slug for draft in drafts)
            )
        ).all()
    }
    created_topic_count = 0
    updated_topic_count = 0
    created_keyword_count = 0
    created_relation_count = 0

    for draft in drafts:
        topic = existing_topics.get(draft.slug)
        if topic is None:
            topic = TopicCluster(
                slug=draft.slug,
                title=draft.title,
                summary=draft.summary,
                category=draft.category.value,
                mention_count=draft.mention_count,
                momentum_score=draft.momentum_score,
                sentiment_score=draft.sentiment_score,
                impact_score=draft.impact_score,
                confidence_score=draft.confidence_score,
                lifecycle_status=LifecycleStatus.EMERGING.value,
                first_seen_at=processed_at,
                last_activity_at=processed_at,
            )
            db.add(topic)
            db.flush()
            created_topic_count += 1
        else:
            topic.title = draft.title
            topic.summary = draft.summary
            topic.category = draft.category.value
            topic.mention_count = draft.mention_count
            topic.momentum_score = draft.momentum_score
            topic.sentiment_score = draft.sentiment_score
            topic.impact_score = draft.impact_score
            topic.confidence_score = draft.confidence_score
            topic.lifecycle_status = LifecycleStatus.ACTIVE.value
            topic.last_activity_at = processed_at
            updated_topic_count += 1

        db.execute(
            delete(KeywordRelation).where(
                KeywordRelation.topic_id == topic.id
            )
        )
        db.execute(
            delete(TopicKeyword).where(TopicKeyword.topic_id == topic.id)
        )
        db.add_all(
            [
                TopicKeyword(
                    topic_id=topic.id,
                    keyword=keyword.keyword,
                    weight=keyword.weight,
                    sentiment_score=keyword.sentiment_score,
                    category=(
                        keyword.category.value
                        if keyword.category is not None
                        else None
                    ),
                    mention_count=keyword.mention_count,
                )
                for keyword in draft.keywords
            ]
        )
        db.add_all(
            [
                KeywordRelation(
                    topic_id=topic.id,
                    source_keyword=relation.source_keyword,
                    target_keyword=relation.target_keyword,
                    strength=relation.strength,
                    cooccurrence_count=relation.cooccurrence_count,
                )
                for relation in draft.relations
            ]
        )
        created_keyword_count += len(draft.keywords)
        created_relation_count += len(draft.relations)

    db.commit()
    return ClusteringResult(
        created_topic_count=created_topic_count,
        updated_topic_count=updated_topic_count,
        created_keyword_count=created_keyword_count,
        created_relation_count=created_relation_count,
    )
