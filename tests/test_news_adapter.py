from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.adapters.news.mock import MockNewsAdapter
from app.adapters.news.rss import RSSNewsAdapter
from app.domains.raw_news.repository import RawNewsEventRepository
from app.domains.raw_news.service import RawNewsService


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


def test_rss_news_adapter_fetch_query_uses_market_locale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published = datetime(2026, 6, 18, 12, 30, tzinfo=timezone.utc)
    captured_urls: list[str] = []
    parsed_feed = SimpleNamespace(
        bozo=False,
        feed=SimpleNamespace(title="Query Feed"),
        entries=[
            {
                "title": "Samsung Electronics expands AI memory output",
                "link": "https://example.com/samsung",
                "summary": "Korean chip demand rises.",
                "published_parsed": published.timetuple(),
            },
            {
                "title": "",
                "link": "https://example.com/empty",
                "summary": "skipped",
            },
        ],
    )

    def parse(url: str) -> Any:
        captured_urls.append(url)
        return parsed_feed

    monkeypatch.setattr("app.adapters.news.rss.feedparser.parse", parse)

    results = RSSNewsAdapter(
        [],
        query_url_template="https://example.com/rss?q={query}&hl={hl}&gl={gl}",
    ).fetch_query("Samsung Electronics", "KOSPI")

    assert captured_urls == [
        "https://example.com/rss?q=Samsung+Electronics&hl=ko&gl=KR"
    ]
    assert len(results) == 1
    assert results[0].title == "Samsung Electronics expands AI memory output"
    assert results[0].source == "Query Feed"
    assert results[0].published_at == published


def test_rss_news_adapter_fetch_query_uses_us_locale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_urls: list[str] = []
    parsed_feed = SimpleNamespace(bozo=False, feed={}, entries=[])

    def parse(url: str) -> Any:
        captured_urls.append(url)
        return parsed_feed

    monkeypatch.setattr("app.adapters.news.rss.feedparser.parse", parse)

    RSSNewsAdapter(
        [],
        query_url_template="https://example.com/rss?q={query}&hl={hl}&gl={gl}",
    ).fetch_query("Apple Inc.", "NASDAQ")

    assert captured_urls == ["https://example.com/rss?q=Apple+Inc.&hl=en-US&gl=US"]


def test_raw_news_service_collect_and_save_with_mock_adapter(db: Session) -> None:
    saved_count = RawNewsService(db).collect_and_save(
        MockNewsAdapter(), ["AAPL", "TSLA"]
    )

    assert saved_count == 4
    assert RawNewsEventRepository(db).get_by_url(
        "https://example.com/mock-news/aapl/1"
    )
