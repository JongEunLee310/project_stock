from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.domains.news_insights.model import (
    EventEvidence,
    ExtractedEvent,
    KeywordRelation,
    SourceDocument,
    TopicCluster,
    TopicInsight,
    TopicKeyword,
)
from app.domains.news_insights.types import (
    DocumentType,
    EventStatus,
    EventType,
    EvidenceRole,
    LifecycleStatus,
    ProcessingStatus,
    SentimentDirection,
    TopicCategory,
)


@dataclass(frozen=True)
class SeededNewsInsights:
    documents: tuple[SourceDocument, ...]
    events: tuple[ExtractedEvent, ...]
    evidence: tuple[EventEvidence, ...]
    topics: tuple[TopicCluster, ...]
    keywords: tuple[TopicKeyword, ...]
    relations: tuple[KeywordRelation, ...]
    insights: tuple[TopicInsight, ...]


def seed_mock_news_insights(
    session: Session,
    *,
    now: datetime | None = None,
) -> SeededNewsInsights:
    """Insert a small connected dataset for contract demonstrations and tests."""
    seeded_at = now or datetime.now(UTC)
    document = SourceDocument(
        document_type=DocumentType.DISCLOSURE.value,
        source_name="DART",
        source_url="https://dart.fss.or.kr/mock/202607210001",
        external_id="202607210001",
        title="반도체 장기 공급계약 체결",
        raw_content="회사는 글로벌 고객사와 장기 공급계약을 체결했다.",
        normalized_content="글로벌 고객사와 반도체 장기 공급계약 체결",
        language="ko",
        published_at=seeded_at - timedelta(hours=2),
        collected_at=seeded_at - timedelta(hours=1, minutes=55),
        content_hash="mock-news-insight-document-00000000000000000000000000000001",
        source_reliability=0.98,
        processing_status=ProcessingStatus.EXTRACTED.value,
    )
    event = ExtractedEvent(
        event_type=EventType.SUPPLY_CONTRACT.value,
        title="글로벌 고객사 장기 공급계약",
        summary="신규 장기 계약으로 반도체 공급 가시성이 높아졌다.",
        importance_score=0.88,
        sentiment_direction=SentimentDirection.POSITIVE.value,
        sentiment_score=0.79,
        confidence_score=0.94,
        occurred_at=seeded_at - timedelta(hours=3),
        detected_at=seeded_at - timedelta(hours=1, minutes=50),
        primary_symbol="005930",
        sector_code="SEMICONDUCTOR",
        event_fingerprint="005930:SUPPLY_CONTRACT:2026-07:GLOBAL_CUSTOMER",
        status=EventStatus.ACTIVE.value,
    )
    topic = TopicCluster(
        slug="semiconductor-long-term-demand",
        title="반도체 장기 수요 회복",
        summary="장기 공급계약과 AI 수요가 공급 가시성을 높이고 있다.",
        category=TopicCategory.DEMAND.value,
        mention_count=12,
        momentum_score=0.81,
        sentiment_score=0.76,
        impact_score=0.87,
        confidence_score=0.9,
        lifecycle_status=LifecycleStatus.RISING.value,
        first_seen_at=seeded_at - timedelta(days=3),
        last_activity_at=seeded_at - timedelta(hours=1),
    )
    session.add_all([document, event, topic])
    session.flush()

    evidence = EventEvidence(
        event_id=event.id,
        document_id=document.id,
        relevance_score=0.96,
        evidence_role=EvidenceRole.PRIMARY.value,
        extracted_quote="글로벌 고객사와 장기 공급계약을 체결했다.",
    )
    keywords = (
        TopicKeyword(
            topic_id=topic.id,
            keyword="장기 공급계약",
            weight=0.92,
            sentiment_score=0.78,
            category=TopicCategory.DEMAND.value,
            mention_count=8,
        ),
        TopicKeyword(
            topic_id=topic.id,
            keyword="AI 반도체",
            weight=0.84,
            sentiment_score=0.74,
            category=TopicCategory.GROWTH.value,
            mention_count=6,
        ),
    )
    relation = KeywordRelation(
        topic_id=topic.id,
        source_keyword="장기 공급계약",
        target_keyword="AI 반도체",
        strength=0.86,
        cooccurrence_count=5,
    )
    insight = TopicInsight(
        topic_id=topic.id,
        version=1,
        executive_summary="장기 계약이 반도체 수요 회복의 가시성을 높인다.",
        why_it_matters="계약 기간 동안 매출 변동성이 낮아질 가능성이 있다.",
        key_evidence=[{"event_id": event.id}],
        risk_points=["고객사 주문 일정 변경"],
        counter_arguments=["계약 규모가 전체 매출에서 차지하는 비중은 제한적일 수 있다."],
        impact_score=0.87,
        confidence_score=0.9,
        model_name="mock-news-intelligence",
        prompt_version="v1",
    )
    session.add_all([evidence, *keywords, relation, insight])
    session.flush()

    return SeededNewsInsights(
        documents=(document,),
        events=(event,),
        evidence=(evidence,),
        topics=(topic,),
        keywords=keywords,
        relations=(relation,),
        insights=(insight,),
    )
