from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.news.categorizer import categorize
from app.domains.news.model import NewsItem


def backfill_news_categories(db: Session) -> int:
    items = db.scalars(
        select(NewsItem).where(NewsItem.category.is_(None)).order_by(NewsItem.id)
    ).all()
    for item in items:
        item.category = categorize(item.title, item.summary)
    db.commit()
    return len(items)
