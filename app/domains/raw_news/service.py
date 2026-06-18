from sqlalchemy.orm import Session

from app.adapters.news.base import NewsAdapter
from app.domains.raw_news.repository import RawNewsEventRepository
from app.domains.raw_news.schema import RawNewsEventCreate


class RawNewsService:
    def __init__(self, db: Session) -> None:
        self.repo = RawNewsEventRepository(db)

    def collect_and_save(self, adapter: NewsAdapter, symbols: list[str]) -> int:
        saved_count = 0
        for result in adapter.fetch(symbols):
            event = self.repo.create_or_skip(
                RawNewsEventCreate(
                    title=result.title,
                    url=result.url,
                    body=result.body,
                    source=result.source,
                    published_at=result.published_at,
                    payload=result.payload,
                )
            )
            if event is not None:
                saved_count += 1
        return saved_count
