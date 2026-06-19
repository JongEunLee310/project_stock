import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.news.model import NewsItem
from app.domains.news.schema import NewsItemCreate, NewsSummaryResult


class NewsItemRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, data: NewsItemCreate) -> NewsItem:
        item = NewsItem(**data.model_dump())
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def update_summary(
        self, news_item_id: int, data: NewsSummaryResult
    ) -> NewsItem:
        item = self.db.get(NewsItem, news_item_id)
        if item is None:
            # Keep direct repository callers from silently updating a missing row.
            raise ValueError("news item not found")

        item.summary = data.summary
        item.sentiment = data.sentiment
        item.impact_level = data.impact_level
        item.positive_factors = json.dumps(data.positive_factors, ensure_ascii=False)
        item.negative_factors = json.dumps(data.negative_factors, ensure_ascii=False)
        self.db.commit()
        self.db.refresh(item)
        return item

    def list_by_asset(self, asset_id: int) -> list[NewsItem]:
        stmt = (
            select(NewsItem)
            .where(NewsItem.asset_id == asset_id)
            .order_by(NewsItem.created_at.desc(), NewsItem.id.desc())
        )
        return list(self.db.scalars(stmt).all())
