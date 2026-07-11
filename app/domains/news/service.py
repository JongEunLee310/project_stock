from sqlalchemy.orm import Session

from app.adapters.llm.gateway import LLMGateway
from app.adapters.llm.privacy import NewsSummarySnapshot
from app.adapters.llm.prompts.news_summary import build_news_summary_system_prompt
from app.adapters.llm.types import LLMTaskType
from app.domains.news.model import NewsItem
from app.domains.news.repository import NewsItemRepository
from app.domains.news.schema import NewsSummaryResult
from app.domains.raw_news.model import RawNewsEvent


_NEWS_CATEGORIES = frozenset(
    {
        "EARNINGS",
        "PRODUCT",
        "PARTNERSHIP",
        "REGULATION",
        "PERSONNEL",
        "CAPITAL",
        "MARKET",
        "OTHER",
    }
)


class NewsAnalysisService:
    def __init__(self, db: Session, gateway: LLMGateway) -> None:
        self.db = db
        self.gateway = gateway
        self.repository = NewsItemRepository(db)

    def summarize(self, news_item_id: int) -> NewsSummaryResult:
        news_item = self.db.get(NewsItem, news_item_id)
        if news_item is None:
            raise ValueError("news item not found")

        completion = self.gateway.complete_json(
            LLMTaskType.NEWS_SUMMARY,
            NewsSummarySnapshot(
                title=news_item.title,
                body=self._body_for(news_item),
            ),
            NewsSummaryResult,
            build_news_summary_system_prompt(),
        )
        output = dict(completion.output)
        category = output.get("category")
        if not isinstance(category, str) or category not in _NEWS_CATEGORIES:
            output["category"] = None
        result = NewsSummaryResult.model_validate(output)
        self.repository.update_summary(news_item_id, result)
        return result

    def _body_for(self, news_item: NewsItem) -> str:
        if news_item.raw_news_event_id is None:
            return news_item.summary or ""

        raw_event = self.db.get(RawNewsEvent, news_item.raw_news_event_id)
        if raw_event is None:
            return news_item.summary or ""
        return raw_event.body or ""
