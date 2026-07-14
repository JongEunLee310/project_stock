from sqlalchemy.orm import Session

from app.domains.assets.model import Asset
from app.domains.news.backfill import backfill_news_categories
from app.domains.news.model import NewsItem


def test_backfill_news_categories_updates_only_null_rows_idempotently(
    db: Session,
) -> None:
    asset = Asset(symbol="AAPL", name="Apple Inc.", market="NASDAQ")
    db.add(asset)
    db.commit()
    db.refresh(asset)
    null_category = NewsItem(
        asset_id=asset.id,
        title="Apple announces dividend increase",
        url="https://example.com/dividend",
        source="Example News",
    )
    existing_category = NewsItem(
        asset_id=asset.id,
        title="Quarterly earnings beat expectations",
        url="https://example.com/earnings",
        source="Example News",
        category="PRODUCT",
    )
    db.add_all([null_category, existing_category])
    db.commit()

    assert backfill_news_categories(db) == 1
    assert null_category.category == "CAPITAL"
    assert existing_category.category == "PRODUCT"
    assert backfill_news_categories(db) == 0
