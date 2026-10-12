import json
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.news.categorizer import categorize
from app.domains.news.model import NewsItem
from app.domains.news.schema import NewsItemCreate, NewsSummaryResult


class NewsItemRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, data: NewsItemCreate) -> NewsItem:
        if data.category is None:
            data = data.model_copy(
                update={"category": categorize(data.title, data.summary)}
            )
        item = NewsItem(**data.model_dump())
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def exists_by_url(self, url: str) -> bool:
        stmt = select(NewsItem.id).where(NewsItem.url == url).limit(1)
        return self.db.scalar(stmt) is not None

    def update_summary(
        self, news_item_id: int, data: NewsSummaryResult
    ) -> NewsItem:
        item = self.db.get(NewsItem, news_item_id)
        if item is None:
            # Keep direct repository callers from silently updating a missing row.
            raise ValueError("news item not found")

        item.summary = data.summary
        if data.category is not None:
            item.category = data.category
        item.sentiment = data.sentiment
        item.impact_level = data.impact_level
        item.positive_factors = json.dumps(data.positive_factors, ensure_ascii=False)
        item.negative_factors = json.dumps(data.negative_factors, ensure_ascii=False)
        self.db.commit()
        self.db.refresh(item)
        return item

    def list_by_raw_event_ids(self, raw_event_ids: list[int]) -> list[NewsItem]:
        stmt = (
            select(NewsItem)
            .where(NewsItem.raw_news_event_id.in_(raw_event_ids))
            .order_by(NewsItem.id)
        )
        return list(self.db.scalars(stmt).all())

    def list_by_asset(self, asset_id: int) -> list[NewsItem]:
        stmt = (
            select(NewsItem)
            .where(NewsItem.asset_id == asset_id)
            .order_by(NewsItem.created_at.desc(), NewsItem.id.desc())
        )
        return list(self.db.scalars(stmt).all())

    def list_by_asset_with_limit(
        self,
        asset_id: int,
        limit: int = 20,
    ) -> list[NewsItem]:
        stmt = (
            select(NewsItem)
            .where(NewsItem.asset_id == asset_id)
            .order_by(
                NewsItem.published_at.desc().nullslast(),
                NewsItem.id.desc(),
            )
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def list_by_asset_created_after(
        self, asset_id: int, created_after: datetime, limit: int
    ) -> list[NewsItem]:
        stmt = (
            select(NewsItem)
            .where(NewsItem.asset_id == asset_id, NewsItem.created_at > created_after)
            .order_by(NewsItem.created_at.desc(), NewsItem.id.desc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt))

    def count_by_asset_created_after(
        self, asset_id: int, created_after: datetime
    ) -> int:
        stmt = select(func.count()).select_from(NewsItem).where(
            NewsItem.asset_id == asset_id, NewsItem.created_at > created_after
        )
        return int(self.db.scalar(stmt) or 0)

    def update_classification(
        self, news_item_id: int, impact_level: str, sentiment: str
    ) -> NewsItem:
        item = self.db.get(NewsItem, news_item_id)
        if item is None:
            raise ValueError("news item not found")
        item.impact_level = impact_level
        item.sentiment = sentiment
        self.db.flush()
        return item
