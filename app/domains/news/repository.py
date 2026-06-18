from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.news.model import NewsItem
from app.domains.news.schema import NewsItemCreate


class NewsItemRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, data: NewsItemCreate) -> NewsItem:
        item = NewsItem(**data.model_dump())
        self.db.add(item)
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
