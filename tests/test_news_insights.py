from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.domains.news_insights.briefing import validate_evidence_event_ids
from app.domains.news_insights.model import (
    AgentRun,
    AgentRunStage,
    EventEvidence,
    ExtractedEvent,
    FundFlowOutlook,
    InvestorFlow,
    KeywordRelation,
    MarketEvent,
    MarketEventTopic,
    SourceDocument,
    TopicCluster,
    TopicInsight,
    TopicKeyword,
)
from app.domains.news_insights.schema import FundFlowRange
from app.domains.news_insights.seed import seed_mock_news_insights
from app.domains.news_insights.types import (
    AgentRunStatus,
    AgentStage,
    DocumentType,
    EvidenceRole,
    EventStatus,
    EventType,
    FlowDirection,
    InvestorType,
    LifecycleStatus,
    MarketEventKind,
    ProcessingStatus,
    SentimentDirection,
    TopicCategory,
)
from tests.conftest import TestingSessionLocal, api_data, set_current_user


SEEDED_AT = datetime(2026, 7, 21, 10, tzinfo=UTC)


@pytest.fixture(autouse=True)
def freeze_news_insights_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.domains.news_insights.service.utcnow",
        lambda: SEEDED_AT,
    )


def seed_news_insights() -> None:
    with TestingSessionLocal() as session:
        seed_mock_news_insights(session, now=SEEDED_AT)
        session.commit()


def add_event(*, detected_at: datetime, symbol: str, fingerprint: str) -> int:
    with TestingSessionLocal() as session:
        event = ExtractedEvent(
            event_type=EventType.BUYBACK.value,
            title=f"{symbol} 자사주 매입",
            summary="주주환원 정책을 강화했다.",
            importance_score=0.72,
            sentiment_direction=SentimentDirection.POSITIVE.value,
            sentiment_score=0.7,
            confidence_score=0.9,
            occurred_at=detected_at - timedelta(minutes=10),
            detected_at=detected_at,
            primary_symbol=symbol,
            sector_code=None,
            event_fingerprint=fingerprint,
            status=EventStatus.ACTIVE.value,
        )
        session.add(event)
        session.commit()
        return event.id


def add_source_document(
    *,
    collected_at: datetime,
    source_name: str,
    content_hash: str,
) -> int:
    with TestingSessionLocal() as session:
        document = SourceDocument(
            document_type=DocumentType.NEWS.value,
            source_name=source_name,
            source_url=f"https://example.com/{content_hash}",
            external_id=None,
            title=f"{source_name} 테스트 문서",
            raw_content="에이전트 파이프라인 집계 테스트 문서다.",
            normalized_content=None,
            language="ko",
            published_at=collected_at - timedelta(minutes=1),
            collected_at=collected_at,
            content_hash=content_hash,
            source_reliability=0.9,
            processing_status=ProcessingStatus.PENDING.value,
        )
        session.add(document)
        session.commit()
        return document.id


def test_overview_returns_four_summary_metrics_and_grounded_briefing(
    client: TestClient,
) -> None:
    set_current_user(1)
    seed_news_insights()

    response = client.get(
        "/api/v1/news-insights/overview",
        params={"market": "KR", "window": "24h", "portfolio_id": 7},
    )

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["as_of"] == "2026-07-21T10:00:00Z"
    assert set(data["summary"]) == {
        "high_importance_events",
        "sentiment_shifts",
        "active_topic_clusters",
        "fund_flow_signals",
    }
    assert all(
        set(metric) == {"count", "change"}
        for metric in data["summary"].values()
    )
    assert data["summary"]["high_importance_events"]["count"] == 1
    assert data["summary"]["active_topic_clusters"]["count"] == 1

    highlights = data["briefing"]["highlights"]
    assert highlights
    existing_event_ids = {
        item["id"]
        for item in cast(
            list[dict[str, Any]],
            api_data(client.get("/api/v1/news-insights/events")),
        )
    }
    for highlight in highlights:
        assert highlight["evidence_count"] == len(highlight["evidence_event_ids"])
        assert set(highlight["evidence_event_ids"]) <= existing_event_ids


def test_events_returns_event_projection_and_opaque_cursor_pages(
    client: TestClient,
) -> None:
    set_current_user(1)
    seed_news_insights()
    middle_id = add_event(
        detected_at=SEEDED_AT - timedelta(minutes=30),
        symbol="000660",
        fingerprint="000660:BUYBACK:middle",
    )
    newest_id = add_event(
        detected_at=SEEDED_AT,
        symbol="035420",
        fingerprint="035420:BUYBACK:newest",
    )

    first_response = client.get(
        "/api/v1/news-insights/events",
        params={"limit": 2},
    )

    assert first_response.status_code == 200
    first_page = cast(list[dict[str, Any]], api_data(first_response))
    assert [item["id"] for item in first_page] == [newest_id, middle_id]
    assert set(first_page[0]) == {
        "id",
        "event_type",
        "document_type",
        "symbol",
        "title",
        "summary",
        "importance",
        "sentiment",
        "source",
        "published_at",
        "evidence_count",
        "topic_ids",
    }
    assert set(first_page[0]["importance"]) == {"level", "score"}
    assert set(first_page[0]["sentiment"]) == {"direction", "score"}
    first_meta = first_response.json()["meta"]
    assert first_meta["limit"] == 2
    assert first_meta["has_more"] is True
    assert isinstance(first_meta["next_cursor"], str)

    second_response = client.get(
        "/api/v1/news-insights/events",
        params={"limit": 2, "cursor": first_meta["next_cursor"]},
    )

    assert second_response.status_code == 200
    second_page = cast(list[dict[str, Any]], api_data(second_response))
    assert len(second_page) == 1
    assert second_page[0]["id"] not in {newest_id, middle_id}
    assert second_page[0]["document_type"] == "DISCLOSURE"
    assert second_page[0]["evidence_count"] == 2
    assert second_response.json()["meta"] == {
        "limit": 2,
        "has_more": False,
        "next_cursor": None,
    }


def test_events_filters_types_symbols_importance_sentiment_and_time(
    client: TestClient,
) -> None:
    set_current_user(1)
    seed_news_insights()

    response = client.get(
        "/api/v1/news-insights/events",
        params={
            "types": EventType.SUPPLY_CONTRACT.value,
            "symbols": "005930",
            "importance": "HIGH",
            "sentiment": "POSITIVE",
            "from": "2026-07-21T00:00:00Z",
            "to": "2026-07-22T00:00:00Z",
            "market": "KR",
        },
    )

    assert response.status_code == 200
    items = cast(list[dict[str, Any]], api_data(response))
    assert len(items) == 1
    assert items[0]["event_type"] == "SUPPLY_CONTRACT"
    assert items[0]["symbol"] == "005930"
    assert items[0]["importance"] == {"level": "HIGH", "score": 0.88}
    assert items[0]["sentiment"] == {"direction": "POSITIVE", "score": 0.79}


def test_events_rejects_invalid_cursor(client: TestClient) -> None:
    set_current_user(1)

    response = client.get(
        "/api/v1/news-insights/events",
        params={"cursor": "not-a-valid-cursor"},
    )

    assert response.status_code == 422


def test_event_detail_returns_evidence_and_related_topics(
    client: TestClient,
) -> None:
    set_current_user(1)
    seed_news_insights()
    with TestingSessionLocal() as session:
        event_id = session.query(ExtractedEvent.id).scalar()

    response = client.get(f"/api/v1/news-insights/events/{event_id}")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert set(data) == {
        "event_type",
        "title",
        "summary",
        "importance",
        "sentiment",
        "affected_symbols",
        "evidence",
        "related_topics",
    }
    assert data["event_type"] == "SUPPLY_CONTRACT"
    assert data["importance"] == {
        "score": 0.88,
        "level": "HIGH",
        "explanation": "신규 장기 계약으로 반도체 공급 가시성이 높아졌다.",
    }
    assert data["sentiment"] == {"direction": "POSITIVE", "score": 0.79}
    assert data["affected_symbols"] == [
        {
            "symbol": "005930",
            "direction": "POSITIVE",
            "exposure_score": 0.96,
            "reason": "신규 장기 계약으로 반도체 공급 가시성이 높아졌다.",
        }
    ]
    assert len(data["evidence"]) == 2
    assert set(data["evidence"][0]) == {
        "document_id",
        "document_type",
        "source",
        "title",
        "published_at",
        "evidence_role",
    }
    assert data["evidence"][0]["document_type"] == "DISCLOSURE"
    assert data["evidence"][0]["source"] == "DART"
    assert data["evidence"][0]["published_at"].endswith("Z")
    assert data["evidence"][0]["evidence_role"] == "PRIMARY"
    assert len(data["related_topics"]) == 1
    assert data["related_topics"][0]["title"] == "반도체 장기 수요 회복"


def test_event_detail_returns_404_for_unknown_event(client: TestClient) -> None:
    set_current_user(1)

    response = client.get("/api/v1/news-insights/events/999")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NEWS_INSIGHT_EVENT_NOT_FOUND"


def test_investor_flows_returns_aggregates_alignment_and_decimal_strings(
    client: TestClient,
) -> None:
    set_current_user(1)
    seed_news_insights()
    with TestingSessionLocal() as session:
        topic_id = session.query(TopicCluster.id).scalar()
        session.add_all(
            [
                InvestorFlow(
                    market="KR",
                    topic_id=topic_id,
                    investor_type=InvestorType.FOREIGN.value,
                    net_value=Decimal("2500000000.0000"),
                    direction=FlowDirection.BUY.value,
                    window="5d",
                    as_of=SEEDED_AT,
                    source_kind="INVESTOR_TYPE",
                ),
                InvestorFlow(
                    market="KR",
                    topic_id=topic_id,
                    investor_type=InvestorType.INSTITUTION.value,
                    net_value=Decimal("-2000000000.0000"),
                    direction=FlowDirection.SELL.value,
                    window="5d",
                    as_of=SEEDED_AT - timedelta(days=1),
                    source_kind="INVESTOR_TYPE",
                ),
                InvestorFlow(
                    market="KR",
                    topic_id=topic_id,
                    investor_type=InvestorType.INSTITUTION.value,
                    net_value=Decimal("-3000000000.0000"),
                    direction=FlowDirection.SELL.value,
                    window="5d",
                    as_of=SEEDED_AT,
                    source_kind="INVESTOR_TYPE",
                ),
            ]
        )
        session.commit()

    response = client.get(
        "/api/v1/news-insights/investor-flows",
        params={"market": "KR", "window": "5d", "topic_id": topic_id},
    )

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["as_of"].endswith("Z")
    assert data["aggregation_windows"] == ["5d"]
    assert data["availability"] == {"available": True, "fallback": None}
    assert data["narrative_alignment"]["aligned"] is True
    assert data["narrative_alignment"]["note"]
    assert data["by_investor_type"] == [
        {
            "investor_type": "FOREIGN",
            "net_value": "15000000000.0000",
            "direction": "BUY",
            "change": 0.0,
        },
        {
            "investor_type": "INSTITUTION",
            "net_value": "-3000000000.0000",
            "direction": "SELL",
            "change": -50.0,
        },
    ]
    assert all(
        isinstance(item["net_value"], str)
        for item in data["by_investor_type"]
    )


def test_investor_flows_uses_requested_window_as_time_range(
    client: TestClient,
) -> None:
    set_current_user(1)
    seed_news_insights()
    with TestingSessionLocal() as session:
        topic_id = session.query(TopicCluster.id).scalar()
        session.add(
            InvestorFlow(
                market="KR",
                topic_id=topic_id,
                investor_type=InvestorType.INSTITUTION.value,
                net_value=Decimal("-1000000000.0000"),
                direction=FlowDirection.SELL.value,
                window="1d",
                as_of=SEEDED_AT,
                source_kind="INVESTOR_TYPE",
            )
        )
        session.commit()

    response = client.get(
        "/api/v1/news-insights/investor-flows",
        params={"market": "KR", "window": "7d"},
    )

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["by_investor_type"] == [
        {
            "investor_type": "FOREIGN",
            "net_value": "12500000000.0000",
            "direction": "BUY",
            "change": 0.0,
        },
        {
            "investor_type": "INSTITUTION",
            "net_value": "-1000000000.0000",
            "direction": "SELL",
            "change": 0.0,
        },
    ]
    assert data["aggregation_windows"] == ["1d", "5d"]
    assert data["availability"] == {"available": True, "fallback": None}


def test_investor_flows_excludes_rows_outside_requested_window(
    client: TestClient,
) -> None:
    set_current_user(1)
    seed_news_insights()
    with TestingSessionLocal() as session:
        flow = session.query(InvestorFlow).one()
        flow.as_of = SEEDED_AT - timedelta(days=2)
        session.commit()

    response = client.get(
        "/api/v1/news-insights/investor-flows",
        params={"market": "KR", "window": "1d"},
    )

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["by_investor_type"] == []
    assert data["aggregation_windows"] is None
    assert data["availability"]["available"] is False


def test_investor_flows_reports_unavailable_market_without_estimation(
    client: TestClient,
) -> None:
    set_current_user(1)
    seed_news_insights()

    response = client.get(
        "/api/v1/news-insights/investor-flows",
        params={"market": "US", "window": "5d"},
    )

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["by_investor_type"] == []
    assert data["aggregation_windows"] is None
    assert data["availability"]["available"] is False
    assert "ETF" in data["availability"]["fallback"]
    assert "거래량" in data["availability"]["fallback"]
    assert data["narrative_alignment"]["aligned"] is False


def test_calendar_returns_upcoming_market_events_with_related_topics(
    client: TestClient,
) -> None:
    set_current_user(1)
    seed_news_insights()
    now = SEEDED_AT
    with TestingSessionLocal() as session:
        topic_id = session.query(TopicCluster.id).scalar()
        included_at = now + timedelta(hours=1)
        included = MarketEvent(
            scheduled_at=included_at,
            event_kind=MarketEventKind.RATE_DECISION.value,
            title="한국은행 기준금리 결정",
            symbol=None,
            market="KR",
            importance_score=0.93,
        )
        excluded_market = MarketEvent(
            scheduled_at=now + timedelta(days=1),
            event_kind=MarketEventKind.EARNINGS.value,
            title="미국 기업 실적 발표",
            symbol="AAPL",
            market="US",
            importance_score=0.8,
        )
        excluded_window = MarketEvent(
            scheduled_at=now + timedelta(days=2),
            event_kind=MarketEventKind.POLICY.value,
            title="장기 정책 일정",
            symbol=None,
            market="KR",
            importance_score=0.7,
        )
        session.add_all([included, excluded_market, excluded_window])
        session.flush()
        session.add(MarketEventTopic(market_event_id=included.id, topic_id=topic_id))
        session.commit()

    response = client.get(
        "/api/v1/news-insights/calendar",
        params={"window": "1d", "market": "kr", "topic_id": topic_id},
    )

    assert response.status_code == 200
    items = cast(list[dict[str, Any]], api_data(response))
    assert items == [
        {
            "scheduled_at": included_at.isoformat().replace("+00:00", "Z"),
            "event_kind": "RATE_DECISION",
            "title": "한국은행 기준금리 결정",
            "symbol": None,
            "market": "KR",
            "importance": 0.93,
            "related_topic_ids": [topic_id],
        }
    ]


def test_agent_runs_returns_latest_verifiable_stage_summary(
    client: TestClient,
) -> None:
    set_current_user(1)
    seed_news_insights()
    with TestingSessionLocal() as session:
        latest = AgentRun(
            started_at=SEEDED_AT + timedelta(minutes=10),
            finished_at=SEEDED_AT + timedelta(minutes=20),
            status=AgentRunStatus.DELAYED.value,
            processed_documents=42,
            extracted_events=7,
            active_topics=3,
            analysis_version="news-intelligence-v3",
        )
        session.add(latest)
        session.flush()
        session.add_all(
            [
                AgentRunStage(
                    agent_run_id=latest.id,
                    stage=AgentStage.COLLECT.value,
                    status=AgentRunStatus.COMPLETED.value,
                    delayed=False,
                ),
                AgentRunStage(
                    agent_run_id=latest.id,
                    stage=AgentStage.EXTRACT.value,
                    status=AgentRunStatus.DELAYED.value,
                    delayed=True,
                ),
            ]
        )
        session.commit()
    add_source_document(
        collected_at=SEEDED_AT + timedelta(minutes=12),
        source_name="파이프라인 소스 A",
        content_hash="agent-run-latest-source-a-1",
    )
    add_source_document(
        collected_at=SEEDED_AT + timedelta(minutes=13),
        source_name="파이프라인 소스 A",
        content_hash="agent-run-latest-source-a-2",
    )
    add_source_document(
        collected_at=SEEDED_AT + timedelta(minutes=14),
        source_name="파이프라인 소스 B",
        content_hash="agent-run-latest-source-b",
    )

    response = client.get("/api/v1/news-insights/agent-runs")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert set(data) == {
        "last_processed_at",
        "processed_documents",
        "extracted_events",
        "active_topics",
        "collected_sources",
        "average_run_duration_seconds",
        "stages",
        "analysis_version",
        "has_delay",
    }
    assert data == {
        "last_processed_at": "2026-07-21T10:20:00Z",
        "processed_documents": 42,
        "extracted_events": 7,
        "active_topics": 3,
        "collected_sources": 2,
        "average_run_duration_seconds": 690,
        "stages": [
            {"name": "COLLECT", "status": "COMPLETED", "delayed": False},
            {"name": "EXTRACT", "status": "DELAYED", "delayed": True},
        ],
        "analysis_version": "news-intelligence-v3",
        "has_delay": True,
    }


def test_agent_runs_returns_null_average_without_completed_runs(
    client: TestClient,
) -> None:
    set_current_user(1)
    with TestingSessionLocal() as session:
        session.add(
            AgentRun(
                started_at=SEEDED_AT - timedelta(minutes=5),
                finished_at=None,
                status=AgentRunStatus.RUNNING.value,
                processed_documents=1,
                extracted_events=0,
                active_topics=0,
                analysis_version="news-intelligence-running",
            )
        )
        session.commit()
    add_source_document(
        collected_at=SEEDED_AT - timedelta(minutes=2),
        source_name="진행중 테스트 소스",
        content_hash="agent-run-running-source",
    )

    response = client.get("/api/v1/news-insights/agent-runs")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["collected_sources"] == 1
    assert data["average_run_duration_seconds"] is None


def test_agent_runs_returns_seeded_metrics_and_zero_sources_without_documents(
    client: TestClient,
) -> None:
    set_current_user(1)
    seed_news_insights()

    response = client.get("/api/v1/news-insights/agent-runs")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["collected_sources"] == 0
    assert data["average_run_duration_seconds"] == 780


def test_agent_runs_average_uses_only_latest_twenty_completed_runs(
    client: TestClient,
) -> None:
    set_current_user(1)
    with TestingSessionLocal() as session:
        runs = []
        for index in range(21):
            started_at = SEEDED_AT - timedelta(hours=2) + timedelta(minutes=index)
            duration = timedelta(hours=1) if index == 0 else timedelta(minutes=1)
            runs.append(
                AgentRun(
                    started_at=started_at,
                    finished_at=started_at + duration,
                    status=AgentRunStatus.COMPLETED.value,
                    processed_documents=index,
                    extracted_events=0,
                    active_topics=0,
                    analysis_version=f"news-intelligence-{index}",
                )
            )
        session.add_all(runs)
        session.commit()

    response = client.get("/api/v1/news-insights/agent-runs")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["average_run_duration_seconds"] == 60


def test_topic_map_returns_typed_nodes_and_keyword_relation_edges(
    client: TestClient,
) -> None:
    set_current_user(1)
    seed_news_insights()

    response = client.get(
        "/api/v1/news-insights/topics/map",
        params={"window": "7d", "market": "KR", "limit": 10},
    )

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert set(data) == {"nodes", "edges"}
    assert {node["type"] for node in data["nodes"]} == {"TOPIC", "KEYWORD"}
    assert all(
        set(node)
        == {
            "id",
            "label",
            "type",
            "mention_count",
            "momentum_score",
            "sentiment_score",
            "category",
        }
        for node in data["nodes"]
    )
    assert len(data["edges"]) == 1
    edge = data["edges"][0]
    assert set(edge) == {"source", "target", "strength", "cooccurrence_count"}
    assert edge["strength"] == 0.86
    assert edge["cooccurrence_count"] == 5
    node_ids = {node["id"] for node in data["nodes"]}
    assert edge["source"] in node_ids
    assert edge["target"] in node_ids
    assert all("sentiment_score" not in item for item in data["edges"])


def test_topic_map_applies_window_and_topic_limit(client: TestClient) -> None:
    set_current_user(1)
    seed_news_insights()
    with TestingSessionLocal() as session:
        stale_topic = TopicCluster(
            slug="stale-topic",
            title="오래된 토픽",
            summary=None,
            category=TopicCategory.MARKET_EVENT.value,
            mention_count=100,
            momentum_score=0.99,
            sentiment_score=0.5,
            impact_score=0.5,
            confidence_score=0.9,
            lifecycle_status=LifecycleStatus.ACTIVE.value,
            first_seen_at=SEEDED_AT - timedelta(days=10),
            last_activity_at=SEEDED_AT - timedelta(days=2),
        )
        session.add(stale_topic)
        session.flush()
        stale_keyword = TopicKeyword(
            topic_id=stale_topic.id,
            keyword="과거 키워드",
            weight=0.99,
            sentiment_score=0.5,
            category=TopicCategory.MARKET_EVENT.value,
            mention_count=100,
        )
        session.add(stale_keyword)

        fresh_topic = TopicCluster(
            slug="fresh-secondary-topic",
            title="신규 보조 토픽",
            summary=None,
            category=TopicCategory.GROWTH.value,
            mention_count=2,
            momentum_score=0.2,
            sentiment_score=0.6,
            impact_score=0.4,
            confidence_score=0.8,
            lifecycle_status=LifecycleStatus.EMERGING.value,
            first_seen_at=SEEDED_AT - timedelta(hours=12),
            last_activity_at=SEEDED_AT - timedelta(minutes=30),
        )
        session.add(fresh_topic)
        session.flush()
        fresh_keywords = (
            TopicKeyword(
                topic_id=fresh_topic.id,
                keyword="신규 키워드 A",
                weight=0.2,
                sentiment_score=0.6,
                category=TopicCategory.GROWTH.value,
                mention_count=2,
            ),
            TopicKeyword(
                topic_id=fresh_topic.id,
                keyword="신규 키워드 B",
                weight=0.1,
                sentiment_score=0.4,
                category=None,
                mention_count=1,
            ),
        )
        session.add_all(fresh_keywords)
        session.flush()
        session.add(
            KeywordRelation(
                topic_id=fresh_topic.id,
                source_keyword=fresh_keywords[0].keyword,
                target_keyword=fresh_keywords[1].keyword,
                strength=0.3,
                cooccurrence_count=1,
            )
        )
        session.commit()

    window_response = client.get(
        "/api/v1/news-insights/topics/map",
        params={"window": "1d", "limit": 10},
    )

    assert window_response.status_code == 200
    window_data = cast(dict[str, Any], api_data(window_response))
    labels = {node["label"] for node in window_data["nodes"]}
    assert "오래된 토픽" not in labels
    assert "과거 키워드" not in labels
    assert "반도체 장기 수요 회복" in labels
    assert "신규 보조 토픽" in labels

    limited_response = client.get(
        "/api/v1/news-insights/topics/map",
        params={"window": "1d", "limit": 1},
    )

    assert limited_response.status_code == 200
    limited_data = cast(dict[str, Any], api_data(limited_response))
    topic_nodes = [
        node for node in limited_data["nodes"] if node["type"] == "TOPIC"
    ]
    assert len(topic_nodes) == 1
    assert topic_nodes[0]["label"] == "반도체 장기 수요 회복"
    assert len(limited_data["edges"]) == 1


def test_briefing_evidence_validation_excludes_unknown_ids() -> None:
    assert validate_evidence_event_ids([3, 999, 2, 3], {1, 2, 3}) == [3, 2]


def test_topic_detail_returns_latest_insight_and_required_fields(
    client: TestClient,
) -> None:
    set_current_user(1)
    seed_news_insights()
    with TestingSessionLocal() as session:
        topic = session.query(TopicCluster).one()
        event = session.query(ExtractedEvent).one()
        session.add(
            TopicInsight(
                topic_id=topic.id,
                version=2,
                executive_summary="최신 장기 수요 인사이트",
                why_it_matters="공급 가시성이 재평가될 수 있다.",
                key_evidence=[{"event_id": event.id}],
                risk_points=["계약 지연"],
                counter_arguments=["단기 실적 영향은 제한적이다."],
                impact_score=0.91,
                confidence_score=0.93,
                model_name="mock-news-intelligence",
                prompt_version="v2",
                created_at=SEEDED_AT,
            )
        )
        topic_id = topic.id
        session.commit()

    response = client.get(f"/api/v1/news-insights/topics/{topic_id}")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert set(data) == {
        "title",
        "tags",
        "lifecycle",
        "scores",
        "affected_symbols",
        "insight",
        "version",
        "updated_at",
    }
    assert data["version"] == 2
    assert data["insight"]["summary"] == "최신 장기 수요 인사이트"
    assert data["insight"]["counter_arguments"] == [
        "단기 실적 영향은 제한적이다."
    ]
    assert data["affected_symbols"][0]["symbol"] == "005930"
    assert data["updated_at"].endswith("Z")


def test_topic_symbols_separates_exposure_from_direction(
    client: TestClient,
) -> None:
    set_current_user(1)
    seed_news_insights()
    with TestingSessionLocal() as session:
        topic_id = session.query(TopicCluster.id).scalar()

    response = client.get(
        f"/api/v1/news-insights/topics/{topic_id}/symbols"
    )

    assert response.status_code == 200
    items = cast(list[dict[str, Any]], api_data(response))
    assert items == [
        {
            "symbol": "005930",
            "exposure_score": 0.91,
            "impact_direction": "POSITIVE",
            "relationship": "DIRECT",
            "valuation_burden": "MEDIUM",
            "portfolio_weight": None,
            "current_signal": None,
        }
    ]
    assert isinstance(items[0]["exposure_score"], float)
    assert isinstance(items[0]["impact_direction"], str)


def test_topic_graph_returns_keyword_nodes_edges_and_references(
    client: TestClient,
) -> None:
    set_current_user(1)
    seed_news_insights()
    with TestingSessionLocal() as session:
        topic_id = session.query(TopicCluster.id).scalar()
        event_id = session.query(ExtractedEvent.id).scalar()

    response = client.get(
        f"/api/v1/news-insights/topics/{topic_id}/graph"
    )

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert set(data) == {"nodes", "edges"}
    assert len(data["nodes"]) == 2
    assert all(
        set(node)
        == {
            "id",
            "label",
            "type",
            "mention_count",
            "sentiment_score",
            "related_event_ids",
            "related_symbols",
        }
        for node in data["nodes"]
    )
    assert {node["type"] for node in data["nodes"]} == {"KEYWORD"}
    assert all(node["related_event_ids"] == [event_id] for node in data["nodes"])
    assert all(node["related_symbols"] == ["005930"] for node in data["nodes"])
    assert {node["sentiment_score"] for node in data["nodes"]} == {0.78, 0.74}

    assert len(data["edges"]) == 1
    edge = data["edges"][0]
    assert set(edge) == {"source", "target", "strength", "cooccurrence_count"}
    assert edge["strength"] == 0.86
    assert edge["cooccurrence_count"] == 5
    node_ids = {node["id"] for node in data["nodes"]}
    assert edge["source"] in node_ids
    assert edge["target"] in node_ids
    assert "sentiment_score" not in edge


def test_topic_trend_returns_aggregated_points_markers_and_sources(
    client: TestClient,
) -> None:
    set_current_user(1)
    seed_news_insights()
    with TestingSessionLocal() as session:
        topic_id = session.query(TopicCluster.id).scalar()

    response = client.get(
        f"/api/v1/news-insights/topics/{topic_id}/trend",
        params={"window": "7d", "interval": "1d"},
    )

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert set(data) == {"points", "markers", "source_distribution"}
    assert data["points"]
    assert set(data["points"][0]) == {
        "timestamp",
        "mention_count",
        "sentiment_score",
        "impact_score",
    }
    assert data["markers"]
    assert set(data["markers"][0]) == {"timestamp", "label", "event_id"}
    assert data["source_distribution"] == [
        {"source_type": "ANALYST_REPORT", "count": 1, "share": 0.5},
        {"source_type": "DISCLOSURE", "count": 1, "share": 0.5},
    ]


def test_topic_evidence_uses_cursor_pagination_and_filters(
    client: TestClient,
) -> None:
    set_current_user(1)
    seed_news_insights()
    with TestingSessionLocal() as session:
        topic = session.query(TopicCluster).one()
        event = session.query(ExtractedEvent).one()
        second_document = SourceDocument(
            document_type=DocumentType.NEWS.value,
            source_name="연합뉴스",
            source_url="https://example.com/second",
            external_id=None,
            title="반도체 공급계약 후속 보도",
            raw_content="후속 보도",
            normalized_content="후속 보도",
            language="ko",
            published_at=SEEDED_AT - timedelta(hours=1),
            collected_at=SEEDED_AT - timedelta(minutes=55),
            content_hash="mock-news-insight-document-00000000000000000000000000000002",
            source_reliability=0.8,
            processing_status=ProcessingStatus.EXTRACTED.value,
        )
        session.add(second_document)
        session.flush()
        session.add(
            EventEvidence(
                event_id=event.id,
                document_id=second_document.id,
                relevance_score=0.8,
                evidence_role=EvidenceRole.SUPPORTING.value,
                extracted_quote="후속 보도",
            )
        )
        topic_id = topic.id
        session.commit()

    first_response = client.get(
        f"/api/v1/news-insights/topics/{topic_id}/evidence",
        params={"limit": 1, "direction": "POSITIVE"},
    )

    assert first_response.status_code == 200
    first_page = cast(list[dict[str, Any]], api_data(first_response))
    assert len(first_page) == 1
    assert set(first_page[0]) == {
        "event_id",
        "document_id",
        "evidence_role",
        "document_type",
        "symbol",
        "title",
        "summary",
        "direction",
        "relevance_score",
        "source",
        "published_at",
    }
    first_meta = first_response.json()["meta"]
    assert first_meta["has_more"] is True
    assert isinstance(first_meta["next_cursor"], str)

    second_response = client.get(
        f"/api/v1/news-insights/topics/{topic_id}/evidence",
        params={"limit": 1, "cursor": first_meta["next_cursor"]},
    )

    assert second_response.status_code == 200
    second_page = cast(list[dict[str, Any]], api_data(second_response))
    assert len(second_page) == 1
    assert second_page[0]["document_id"] != first_page[0]["document_id"]
    second_meta = second_response.json()["meta"]
    assert second_meta["has_more"] is True

    third_response = client.get(
        f"/api/v1/news-insights/topics/{topic_id}/evidence",
        params={"limit": 1, "cursor": second_meta["next_cursor"]},
    )
    assert third_response.status_code == 200
    third_page = cast(list[dict[str, Any]], api_data(third_response))
    assert len(third_page) == 1
    assert third_page[0]["document_id"] not in {
        first_page[0]["document_id"],
        second_page[0]["document_id"],
    }
    assert third_response.json()["meta"]["has_more"] is False

    filtered_response = client.get(
        f"/api/v1/news-insights/topics/{topic_id}/evidence",
        params={"types": "DISCLOSURE"},
    )
    filtered_page = cast(list[dict[str, Any]], api_data(filtered_response))
    assert filtered_response.status_code == 200
    assert [item["document_type"] for item in filtered_page] == ["DISCLOSURE"]


def test_topic_detail_routes_return_404_for_unknown_topic(
    client: TestClient,
) -> None:
    set_current_user(1)

    for suffix in ("", "/trend", "/evidence", "/symbols", "/graph"):
        response = client.get(f"/api/v1/news-insights/topics/999{suffix}")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NEWS_INSIGHT_TOPIC_NOT_FOUND"


def test_fund_flow_outlook_returns_latest_quantitative_range(
    client: TestClient,
) -> None:
    set_current_user(1)
    seed_news_insights()

    response = client.get(
        "/api/v1/news-insights/fund-flow-outlook",
        params={"market": "KR"},
    )

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert set(data) == {"as_of", "analysis_version", "items"}
    assert data["as_of"].endswith("Z")
    assert data["analysis_version"] == "mock-news-intelligence-v3"
    assert data["items"]
    item = next(item for item in data["items"] if item["sector"] == "반도체")
    assert set(item) == {
        "sector",
        "direction",
        "likelihood",
        "estimated_flow",
        "horizon",
        "confidence",
        "key_assumptions",
        "risk_factors",
    }
    assert item["direction"] in {"INFLOW", "OUTFLOW", "NEUTRAL"}
    assert item["likelihood"] in {"LOW", "MEDIUM", "HIGH"}
    assert item["estimated_flow"] == {
        "low": "800000000000.0000",
        "high": "1800000000000.0000",
        "currency": "KRW",
    }
    assert isinstance(item["estimated_flow"]["low"], str)
    assert isinstance(item["estimated_flow"]["high"], str)
    assert item["key_assumptions"]
    assert item["risk_factors"]


def test_topic_scenarios_returns_all_three_kinds(client: TestClient) -> None:
    set_current_user(1)
    seed_news_insights()
    with TestingSessionLocal() as session:
        topic_id = session.query(TopicCluster.id).scalar()

    response = client.get(
        f"/api/v1/news-insights/topics/{topic_id}/scenarios"
    )

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert set(data) == {"topic_id", "analysis_version", "as_of", "scenarios"}
    assert data["topic_id"] == topic_id
    assert data["analysis_version"] == "mock-news-intelligence-v3"
    assert data["as_of"].endswith("Z")
    assert {item["scenario_kind"] for item in data["scenarios"]} == {
        "OPTIMISTIC",
        "BASE",
        "CONSERVATIVE",
    }
    assert len(data["scenarios"]) == 3
    assert abs(sum(item["weight"] for item in data["scenarios"]) - 1.0) < 1e-9
    assert all(item["invalidation_conditions"] for item in data["scenarios"])
    scenarios = {
        item["scenario_kind"]: item["expected_net_flow"]
        for item in data["scenarios"]
    }
    assert scenarios["OPTIMISTIC"] == {
        "low": "1800000000000.0000",
        "high": "3000000000000.0000",
        "currency": "KRW",
    }
    assert scenarios["BASE"] == {
        "low": "800000000000.0000",
        "high": "1800000000000.0000",
        "currency": "KRW",
    }
    assert scenarios["CONSERVATIVE"] is None


def test_fund_flow_range_distinguishes_zero_from_unavailable(
    client: TestClient,
) -> None:
    set_current_user(1)
    seed_news_insights()
    with TestingSessionLocal() as session:
        outlooks = session.query(FundFlowOutlook).order_by(FundFlowOutlook.id).all()
        outlooks[0].estimated_flow_low = Decimal("0")
        outlooks[0].estimated_flow_high = Decimal("0")
        outlooks[0].estimated_flow_currency = "KRW"
        outlooks[1].estimated_flow_low = Decimal("0")
        outlooks[1].estimated_flow_high = None
        outlooks[1].estimated_flow_currency = "KRW"
        session.commit()

    response = client.get("/api/v1/news-insights/fund-flow-outlook")

    items = {
        item["sector"]: item["estimated_flow"]
        for item in cast(dict[str, Any], api_data(response))["items"]
    }
    assert items["반도체"] == {
        "low": "0.0000",
        "high": "0.0000",
        "currency": "KRW",
    }
    assert items["2차전지"] is None


def test_fund_flow_range_rejects_low_greater_than_high() -> None:
    with pytest.raises(ValidationError, match="low must be less than or equal to high"):
        FundFlowRange(
            low=Decimal("1"),
            high=Decimal("0"),
            currency="KRW",
        )


def test_topic_explanation_returns_factors_and_required_counter_view(
    client: TestClient,
) -> None:
    set_current_user(1)
    seed_news_insights()
    with TestingSessionLocal() as session:
        topic_id = session.query(TopicCluster.id).scalar()

    response = client.get(
        f"/api/v1/news-insights/topics/{topic_id}/explanation"
    )

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert set(data) == {"factors", "meta", "counter_view"}
    assert abs(
        sum(item["contribution_ratio"] for item in data["factors"]) - 1.0
    ) < 1e-9
    assert data["meta"]["analysis_version"] == "mock-news-intelligence-v3"
    assert data["meta"]["counter_argument_count"] >= 1
    assert data["counter_view"]["counter_arguments"]
    assert data["counter_view"]["invalidation_conditions"]
    assert set(data["counter_view"]["already_priced_in"]) == {"likely", "note"}
    contradicting = data["counter_view"]["contradicting_evidence"]
    assert contradicting
    assert set(contradicting[0]) == {
        "event_id",
        "document_id",
        "title",
        "source",
        "published_at",
    }
    assert contradicting[0]["published_at"].endswith("Z")


def test_phase3_topic_routes_return_404_for_unknown_topic(
    client: TestClient,
) -> None:
    set_current_user(1)

    for suffix in ("/scenarios", "/explanation"):
        response = client.get(f"/api/v1/news-insights/topics/999{suffix}")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NEWS_INSIGHT_TOPIC_NOT_FOUND"
