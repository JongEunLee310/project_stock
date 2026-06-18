from collections.abc import Generator
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.domains.assets.model import Asset
from app.domains.news.repository import NewsItemRepository
from app.domains.news.schema import NewsItemCreate
from app.domains.raw_news.model import RawNewsEvent


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db() -> Generator[Session, None, None]:
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def create_asset(db: Session, symbol: str = "AAPL") -> Asset:
    asset = Asset(symbol=symbol, name=f"{symbol} Inc.", market="NASDAQ")
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def create_raw_news_event(db: Session) -> RawNewsEvent:
    event = RawNewsEvent(
        title="Apple supplier expands production",
        url="https://example.com/news/raw",
        source="Example News",
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def news_item_payload(asset_id: int, raw_news_event_id: int | None = None) -> NewsItemCreate:
    return NewsItemCreate(
        raw_news_event_id=raw_news_event_id,
        asset_id=asset_id,
        title="Apple supplier expands production",
        url="https://example.com/news/normalized",
        source="Example News",
        published_at=datetime(2026, 6, 18, tzinfo=timezone.utc),
        summary="Production capacity increased.",
        sentiment="positive",
        impact_level="medium",
    )


def test_create_news_item_success(db: Session) -> None:
    asset = create_asset(db)
    raw_event = create_raw_news_event(db)

    item = NewsItemRepository(db).create(news_item_payload(asset.id, raw_event.id))

    assert item.id == 1
    assert item.raw_news_event_id == raw_event.id
    assert item.asset_id == asset.id
    assert item.title == "Apple supplier expands production"
    assert item.summary == "Production capacity increased."
    assert item.sentiment == "positive"
    assert item.impact_level == "medium"


def test_list_news_items_by_asset(db: Session) -> None:
    repo = NewsItemRepository(db)
    target_asset = create_asset(db, "AAPL")
    other_asset = create_asset(db, "MSFT")
    target_item = repo.create(news_item_payload(target_asset.id))
    repo.create(
        NewsItemCreate(
            asset_id=other_asset.id,
            title="Microsoft launches product",
            url="https://example.com/news/msft",
            source="Example News",
        )
    )

    items = repo.list_by_asset(target_asset.id)

    assert items == [target_item]
