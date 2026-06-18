from datetime import datetime, timezone

from app.adapters.news.base import NewsAdapter, NewsAdapterResult


class MockNewsAdapter(NewsAdapter):
    def fetch(self, symbols: list[str]) -> list[NewsAdapterResult]:
        results: list[NewsAdapterResult] = []
        for symbol in symbols:
            for index in range(1, 3):
                results.append(
                    NewsAdapterResult(
                        title=f"{symbol} mock news {index}",
                        url=f"https://example.com/mock-news/{symbol.lower()}/{index}",
                        body=f"Mock news body for {symbol} #{index}",
                        source="mock",
                        published_at=datetime.now(timezone.utc),
                        payload={"symbol": symbol, "index": index},
                    )
                )
        return results
