import logging
from datetime import datetime, timezone
from time import struct_time
from typing import Any

import feedparser  # type: ignore[import-untyped]

from app.adapters.news.base import NewsAdapter, NewsAdapterResult

logger = logging.getLogger(__name__)


class RSSNewsAdapter(NewsAdapter):
    def __init__(self, feed_urls: list[str]) -> None:
        self.feed_urls = feed_urls

    def fetch(self, symbols: list[str]) -> list[NewsAdapterResult]:
        normalized_symbols = [symbol.lower() for symbol in symbols]
        results: list[NewsAdapterResult] = []

        for feed_url in self.feed_urls:
            try:
                parsed_feed = feedparser.parse(feed_url)
            except Exception:
                logger.exception("failed to parse RSS feed: %s", feed_url)
                continue

            if getattr(parsed_feed, "bozo", False):
                logger.error("failed to parse RSS feed: %s", feed_url)
                continue

            feed_title = _get_nested_value(parsed_feed, "feed", "title") or feed_url
            for entry in getattr(parsed_feed, "entries", []):
                title = str(_get_value(entry, "title") or "")
                summary = str(_get_value(entry, "summary") or "")
                haystack = f"{title} {summary}".lower()
                if normalized_symbols and not any(
                    symbol in haystack for symbol in normalized_symbols
                ):
                    continue

                link = str(_get_value(entry, "link") or "")
                if not title or not link:
                    continue

                results.append(
                    NewsAdapterResult(
                        title=title,
                        url=link,
                        body=summary or None,
                        source=str(feed_title),
                        published_at=_published_at(entry),
                        payload=dict(entry),
                    )
                )

        return results


def _published_at(entry: Any) -> datetime | None:
    published_parsed = _get_value(entry, "published_parsed")
    if not isinstance(published_parsed, struct_time):
        return None
    return datetime(*published_parsed[:6], tzinfo=timezone.utc)


def _get_value(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _get_nested_value(value: Any, key: str, nested_key: str) -> Any:
    parent = _get_value(value, key)
    if parent is None:
        return None
    if isinstance(parent, dict):
        return parent.get(nested_key)
    return getattr(parent, nested_key, None)
