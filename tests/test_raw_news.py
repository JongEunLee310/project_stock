from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.adapters.news.base import NewsAdapterResult
from app.domains.ingestion.schema import ProcessingStatus
from app.domains.raw_news.model import RawNewsEvent
from app.domains.raw_news.repository import RawNewsEventRepository
from app.domains.raw_news.schema import RawNewsEventCreate
from app.domains.raw_news.service import RawNewsService


def raw_news_payload(url: str = "https://example.com/news/1") -> RawNewsEventCreate:
    return RawNewsEventCreate(
        title="Apple supplier expands production",
        url=url,
        body="Full article text",
        source="Example News",
        published_at=datetime(2026, 6, 18, tzinfo=timezone.utc),
        payload={"id": "external-1"},
    )


def test_create_raw_news_event_success(db: Session) -> None:
    event = RawNewsEventRepository(db).create_or_skip(raw_news_payload())

    assert event is not None
    assert event.id == 1
    assert event.title == "Apple supplier expands production"
    assert event.url == "https://example.com/news/1"
    assert event.source == "Example News"
    assert event.payload == {"id": "external-1"}


def test_create_or_skip_returns_none_for_duplicate_url(db: Session) -> None:
    repo = RawNewsEventRepository(db)
    first_event = repo.create_or_skip(raw_news_payload())

    duplicate_event = repo.create_or_skip(raw_news_payload())

    assert first_event is not None
    assert duplicate_event is None
    assert repo.get_by_url("https://example.com/news/1") is not None


def test_collected_at_is_set_automatically(db: Session) -> None:
    event = RawNewsEventRepository(db).create_or_skip(raw_news_payload())

    assert event is not None
    assert event.collected_at is not None


def test_save_with_symbol_tags_raw_news_event(db: Session) -> None:
    result = NewsAdapterResult(
        title="Apple launches new chip",
        url="https://example.com/news/apple-chip",
        body="Apple supplier update",
        source="Example News",
        published_at=datetime(2026, 6, 18, tzinfo=timezone.utc),
        payload={"fixture": True},
    )

    event = RawNewsService(db).save_with_symbol(result, "AAPL", "NASDAQ")

    assert event is not None
    assert event.symbol == "AAPL"
    assert event.market == "NASDAQ"


def test_raw_news_service_defaults_processing_status_to_fetched(db: Session) -> None:
    result = NewsAdapterResult(
        title="Apple launches new chip",
        url="https://example.com/news/apple-chip-status",
        body="Apple supplier update",
        source="Example News",
        published_at=datetime(2026, 6, 18, tzinfo=timezone.utc),
        payload={"fixture": True},
    )

    event = RawNewsService(db).save_with_symbol(result, "AAPL", "NASDAQ")

    assert event is not None
    assert event.processing_status == ProcessingStatus.FETCHED.value


def test_raw_news_processing_status_accepts_pipeline_states(db: Session) -> None:
    normalized_event = RawNewsEvent(
        title="Normalized event",
        url="https://example.com/news/normalized",
        source="Example News",
        processing_status=ProcessingStatus.NORMALIZED.value,
    )
    failed_event = RawNewsEvent(
        title="Failed event",
        url="https://example.com/news/failed",
        source="Example News",
        processing_status=ProcessingStatus.FAILED.value,
    )
    db.add_all([normalized_event, failed_event])
    db.commit()

    statuses = {event.processing_status for event in (normalized_event, failed_event)}

    assert ProcessingStatus.NORMALIZED.value in statuses
    assert ProcessingStatus.FAILED.value in statuses
