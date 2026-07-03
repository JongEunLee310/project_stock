from datetime import UTC, datetime, timezone, timedelta

from sqlalchemy.orm import Session

from app.domains.news.normalizer import NewsNormalizer
from app.domains.raw_news.model import RawNewsEvent


def test_news_normalizer_canonicalizes_fields() -> None:
    normalizer = NewsNormalizer()
    naive_published_at = datetime(2026, 6, 18, 12, 30)
    offset_published_at = datetime(
        2026,
        6,
        18,
        21,
        30,
        tzinfo=timezone(timedelta(hours=9)),
    )

    assert normalizer.canonicalize_symbol("NASDAQ:aapl.o") == "AAPL"
    assert normalizer.canonicalize_market(" nasdaq ") == "NASDAQ"
    assert (
        normalizer.canonicalize_url("https://EXAMPLE.com/news/apple/#section")
        == "https://example.com/news/apple"
    )
    assert normalizer.normalize_published_at(naive_published_at) == datetime(
        2026,
        6,
        18,
        12,
        30,
        tzinfo=UTC,
    )
    assert normalizer.normalize_published_at(offset_published_at) == datetime(
        2026,
        6,
        18,
        12,
        30,
        tzinfo=UTC,
    )


def test_news_normalizer_maps_raw_event_to_news_item_create(db: Session) -> None:
    event = RawNewsEvent(
        id=123,
        title="Apple supplier expands production",
        url="https://EXAMPLE.com/news/apple/#fragment",
        source=" Example News ",
        published_at=datetime(2026, 6, 18, 12, 30),
        symbol="NASDAQ:AAPL",
        market=" nasdaq ",
    )

    data = NewsNormalizer().to_news_item_create(event, asset_id=456)

    assert data.raw_news_event_id == 123
    assert data.asset_id == 456
    assert data.title == "Apple supplier expands production"
    assert data.url == "https://example.com/news/apple"
    assert data.source == "Example News"
    assert data.published_at == datetime(2026, 6, 18, 12, 30, tzinfo=UTC)
    assert data.summary is None
    assert data.sentiment is None
    assert data.impact_level is None
