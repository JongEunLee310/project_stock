from collections.abc import Generator
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.adapters.news.mock import MockNewsAdapter
from app.adapters.news.rss import RSSNewsAdapter
from app.db.base import Base
from app.domains.raw_news.repository import RawNewsEventRepository
from app.domains.raw_news.service import RawNewsService

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db() -> Generator[Session, None, None]:
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_mock_news_adapter_returns_two_items_per_symbol() -> None:
    results = MockNewsAdapter().fetch(["AAPL", "TSLA"])

    assert len(results) == 4
    assert {result.source for result in results} == {"mock"}


def test_rss_news_adapter_parses_matching_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published = datetime(2026, 6, 18, 12, 30, tzinfo=timezone.utc)
    parsed_feed = SimpleNamespace(
        bozo=False,
        feed=SimpleNamespace(title="Example Feed"),
        entries=[
            {
                "title": "AAPL supplier expands production",
                "link": "https://example.com/aapl",
                "summary": "Apple demand is rising.",
                "published_parsed": published.timetuple(),
            },
            {
                "title": "Macro update",
                "link": "https://example.com/macro",
                "summary": "Rates remain steady.",
                "published_parsed": published.timetuple(),
            },
        ],
    )

    def parse(_: str) -> Any:
        return parsed_feed

    monkeypatch.setattr("app.adapters.news.rss.feedparser.parse", parse)

    results = RSSNewsAdapter(["https://example.com/rss"]).fetch(["aapl"])

    assert len(results) == 1
    assert results[0].title == "AAPL supplier expands production"
    assert results[0].url == "https://example.com/aapl"
    assert results[0].body == "Apple demand is rising."
    assert results[0].source == "Example Feed"
    assert results[0].published_at == published


def test_rss_news_adapter_skips_failed_feed(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def parse(_: str) -> Any:
        raise RuntimeError("feed unavailable")

    monkeypatch.setattr("app.adapters.news.rss.feedparser.parse", parse)

    results = RSSNewsAdapter(["https://example.com/rss"]).fetch(["AAPL"])

    assert results == []
    assert "failed to parse RSS feed" in caplog.text


def test_raw_news_service_collect_and_save_with_mock_adapter(db: Session) -> None:
    saved_count = RawNewsService(db).collect_and_save(
        MockNewsAdapter(), ["AAPL", "TSLA"]
    )

    assert saved_count == 4
    assert RawNewsEventRepository(db).get_by_url(
        "https://example.com/mock-news/aapl/1"
    )
