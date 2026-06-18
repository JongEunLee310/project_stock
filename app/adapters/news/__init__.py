from app.adapters.news.base import NewsAdapter, NewsAdapterResult
from app.adapters.news.mock import MockNewsAdapter
from app.adapters.news.rss import RSSNewsAdapter

__all__ = [
    "MockNewsAdapter",
    "NewsAdapter",
    "NewsAdapterResult",
    "RSSNewsAdapter",
]
