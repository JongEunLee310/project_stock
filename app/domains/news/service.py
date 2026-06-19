from sqlalchemy.orm import Session

from app.adapters.llm.base import LLMClient
from app.adapters.llm.prompts.news_summary import build_news_summary_messages
from app.domains.news.model import NewsItem
from app.domains.news.repository import NewsItemRepository
from app.domains.news.schema import NewsSummaryResult
from app.domains.raw_news.model import RawNewsEvent


class NewsAnalysisService:
    def __init__(self, db: Session, llm_client: LLMClient) -> None:
        self.db = db
        self.llm_client = llm_client
        self.repository = NewsItemRepository(db)

    def summarize(self, news_item_id: int) -> NewsSummaryResult:
        news_item = self.db.get(NewsItem, news_item_id)
        if news_item is None:
            raise ValueError("news item not found")

        messages = build_news_summary_messages(
            news_item.title,
            self._body_for(news_item),
        )
        raw_result = self.llm_client.complete_json(messages, NewsSummaryResult)
        result = NewsSummaryResult.model_validate(raw_result)
        self.repository.update_summary(news_item_id, result)
        return result

    def _body_for(self, news_item: NewsItem) -> str:
        if news_item.raw_news_event_id is None:
            return news_item.summary or ""

        raw_event = self.db.get(RawNewsEvent, news_item.raw_news_event_id)
        if raw_event is None:
            return news_item.summary or ""
        return raw_event.body or ""
