from datetime import UTC, datetime, timedelta

from app.domains.ingestion.schema import DataQualityStatus, ValidationErrorReason
from app.domains.news.schema import NewsItemCreate
from app.domains.news.validator import NewsValidator, _STALE_AFTER_DAYS


def test_news_validator_rejects_missing_required_field() -> None:
    outcome = NewsValidator().validate(
        news_item(title=" "),
        now=datetime(2026, 7, 3, tzinfo=UTC),
    )

    assert outcome.status == DataQualityStatus.INVALID
    assert outcome.reasons == [ValidationErrorReason.MISSING_REQUIRED_FIELD]


def test_news_validator_rejects_future_published_at() -> None:
    now = datetime(2026, 7, 3, tzinfo=UTC)

    outcome = NewsValidator().validate(
        news_item(published_at=now + timedelta(minutes=1)),
        now=now,
    )

    assert outcome.status == DataQualityStatus.INVALID
    assert outcome.reasons == [ValidationErrorReason.FUTURE_TIMESTAMP]


def test_news_validator_marks_stale_after_threshold() -> None:
    now = datetime(2026, 7, 3, tzinfo=UTC)

    outcome = NewsValidator().validate(
        news_item(published_at=now - timedelta(days=_STALE_AFTER_DAYS + 1)),
        now=now,
    )

    assert outcome.status == DataQualityStatus.STALE
    assert outcome.reasons == [ValidationErrorReason.STALE]


def test_news_validator_accepts_valid_news() -> None:
    now = datetime(2026, 7, 3, tzinfo=UTC)

    outcome = NewsValidator().validate(
        news_item(published_at=now - timedelta(days=1)),
        now=now,
    )

    assert outcome.status == DataQualityStatus.VALID
    assert outcome.reasons == []


def news_item(
    title: str = "Apple supplier expands",
    url: str = "https://example.com/apple",
    source: str = "fixture",
    published_at: datetime | None = datetime(2026, 7, 2, tzinfo=UTC),
) -> NewsItemCreate:
    return NewsItemCreate(
        raw_news_event_id=1,
        asset_id=1,
        title=title,
        url=url,
        source=source,
        published_at=published_at,
    )
