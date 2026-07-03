from datetime import UTC, datetime
from urllib.parse import urlsplit, urlunsplit

from app.domains.news.schema import NewsItemCreate
from app.domains.raw_news.model import RawNewsEvent


class NewsNormalizer:
    def canonicalize_symbol(self, symbol: str) -> str:
        value = symbol.strip()
        if ":" in value:
            value = value.rsplit(":", maxsplit=1)[-1]
        if "." in value:
            value = value.split(".", maxsplit=1)[0]
        return value.upper()

    def canonicalize_market(self, market: str) -> str:
        return market.strip().upper()

    def canonicalize_url(self, url: str) -> str:
        parts = urlsplit(url.strip())
        netloc = parts.netloc.lower()
        path = parts.path.rstrip("/")
        return urlunsplit((parts.scheme, netloc, path, parts.query, ""))

    def normalize_published_at(self, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def to_news_item_create(
        self,
        event: RawNewsEvent,
        asset_id: int,
    ) -> NewsItemCreate:
        return NewsItemCreate(
            raw_news_event_id=event.id,
            asset_id=asset_id,
            title=event.title,
            url=self.canonicalize_url(event.url),
            source=event.source.strip(),
            published_at=self.normalize_published_at(event.published_at),
        )
