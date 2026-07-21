from datetime import UTC, datetime, timedelta
from typing import Any, cast

from fastapi.testclient import TestClient

from app.domains.news_insights.briefing import validate_evidence_event_ids
from app.domains.news_insights.model import ExtractedEvent
from app.domains.news_insights.seed import seed_mock_news_insights
from app.domains.news_insights.types import (
    EventStatus,
    EventType,
    SentimentDirection,
)
from tests.conftest import TestingSessionLocal, api_data, set_current_user


SEEDED_AT = datetime(2026, 7, 21, 10, tzinfo=UTC)


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
    assert data["as_of"].endswith("Z")
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
    assert second_page[0]["evidence_count"] == 1
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


def test_briefing_evidence_validation_excludes_unknown_ids() -> None:
    assert validate_evidence_event_ids([3, 999, 2, 3], {1, 2, 3}) == [3, 2]
