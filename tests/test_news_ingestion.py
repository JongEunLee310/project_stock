from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.news.base import NewsAdapter, NewsAdapterResult
from app.domains.assets.model import Asset
from app.domains.ingestion.schema import ProcessingStatus
from app.domains.news.model import NewsItem
from app.domains.portfolios.model import Portfolio, Position
from app.domains.raw_news.ingestion_service import NewsIngestionService
from app.domains.raw_news.model import RawNewsEvent
from app.domains.raw_news.universe import NewsUniverseResolver
from app.domains.watchlists.model import Watchlist, WatchlistItem


def test_news_ingestion_tags_deduplicates_and_continues_after_failure(
    db: Session,
) -> None:
    adapter = MixedNewsAdapter(
        {
            "Apple Inc.": [
                news_result("Apple supplier expands", "https://example.com/apple-1"),
                news_result("Apple supplier expands", "https://example.com/shared"),
            ],
            "Samsung Electronics": [
                news_result("Samsung memory expands", "https://example.com/shared"),
                news_result("Samsung foundry update", "https://example.com/samsung-1"),
            ],
        },
        failing_queries={"Failure Corp."},
    )

    result = NewsIngestionService(db).collect_and_save(
        adapter,
        [
            ("AAPL", "NASDAQ", "Apple Inc."),
            ("FAIL", "NASDAQ", "Failure Corp."),
            ("005930", "KOSPI", "Samsung Electronics"),
        ],
    )

    assert result.target_count == 3
    assert result.success_count == 2
    assert result.failure_count == 1
    assert result.received_count == 4
    assert result.saved_count == 3
    assert result.skipped_count == 1

    rows = db.scalars(select(RawNewsEvent).order_by(RawNewsEvent.id)).all()
    assert [(row.symbol, row.market) for row in rows] == [
        ("AAPL", "NASDAQ"),
        ("AAPL", "NASDAQ"),
        ("005930", "KOSPI"),
    ]


def test_news_ingestion_normalizes_saved_raw_event(db: Session) -> None:
    asset = Asset(symbol="AAPL", name="Apple Inc.", market="NASDAQ")
    db.add(asset)
    db.commit()
    db.refresh(asset)
    adapter = MixedNewsAdapter(
        {
            "Apple Inc.": [
                news_result(
                    "Apple launches new product",
                    "https://EXAMPLE.com/apple-1/#section",
                )
            ]
        }
    )

    result = NewsIngestionService(db).collect_and_save(
        adapter,
        [("aapl.o", " nasdaq ", "Apple Inc.")],
    )

    assert result.saved_count == 1
    assert result.normalized_count == 1
    raw_event = db.scalars(select(RawNewsEvent)).one()
    news_item = db.scalars(select(NewsItem)).one()
    assert raw_event.processing_status == ProcessingStatus.NORMALIZED.value
    assert news_item.raw_news_event_id == raw_event.id
    assert news_item.asset_id == asset.id
    assert news_item.title == "Apple launches new product"
    assert news_item.url == "https://example.com/apple-1"
    assert news_item.source == "fixture"
    assert news_item.summary is None
    assert news_item.category == "PRODUCT"
    assert news_item.sentiment is None
    assert news_item.impact_level is None


def test_news_ingestion_marks_invalid_news_failed_without_news_item(
    db: Session,
) -> None:
    db.add(Asset(symbol="AAPL", name="Apple Inc.", market="NASDAQ"))
    db.commit()
    adapter = MixedNewsAdapter(
        {
            "Apple Inc.": [
                news_result(
                    "Apple future update",
                    "https://example.com/apple-future",
                    published_at=datetime.now(timezone.utc) + timedelta(days=1),
                )
            ]
        }
    )

    result = NewsIngestionService(db).collect_and_save(
        adapter,
        [("AAPL", "NASDAQ", "Apple Inc.")],
    )

    assert result.saved_count == 1
    assert result.normalized_count == 0
    raw_event = db.scalars(select(RawNewsEvent)).one()
    assert raw_event.processing_status == ProcessingStatus.FAILED.value
    assert db.scalars(select(NewsItem)).all() == []


def test_news_ingestion_leaves_unresolved_asset_fetched(db: Session) -> None:
    adapter = MixedNewsAdapter(
        {"Missing Corp.": [news_result("Missing update", "https://example.com/missing")]}
    )

    result = NewsIngestionService(db).collect_and_save(
        adapter,
        [("MISS", "NASDAQ", "Missing Corp.")],
    )

    assert result.saved_count == 1
    assert result.normalized_count == 0
    raw_event = db.scalars(select(RawNewsEvent)).one()
    assert raw_event.processing_status == ProcessingStatus.FETCHED.value
    assert db.scalars(select(NewsItem)).all() == []


def test_news_ingestion_deduplicates_canonical_news_item_url(db: Session) -> None:
    db.add(Asset(symbol="AAPL", name="Apple Inc.", market="NASDAQ"))
    db.commit()
    adapter = MixedNewsAdapter(
        {
            "Apple Inc.": [
                news_result("Apple one", "https://EXAMPLE.com/apple"),
                news_result("Apple duplicate", "https://example.com/apple/#fragment"),
            ]
        }
    )

    result = NewsIngestionService(db).collect_and_save(
        adapter,
        [("AAPL", "NASDAQ", "Apple Inc.")],
    )

    assert result.saved_count == 2
    assert result.normalized_count == 2
    raw_events = db.scalars(select(RawNewsEvent).order_by(RawNewsEvent.id)).all()
    assert [event.processing_status for event in raw_events] == [
        ProcessingStatus.NORMALIZED.value,
        ProcessingStatus.NORMALIZED.value,
    ]
    news_items = db.scalars(select(NewsItem)).all()
    assert len(news_items) == 1
    assert news_items[0].url == "https://example.com/apple"


def test_news_universe_resolver_deduplicates_watchlist_and_portfolio(
    db: Session,
) -> None:
    aapl, samsung = seed_assets(db)
    watchlist = Watchlist(user_id=1, name="Main")
    portfolio = Portfolio(user_id=1, name="Core")
    db.add_all([watchlist, portfolio])
    db.commit()
    db.refresh(watchlist)
    db.refresh(portfolio)
    db.add_all(
        [
            WatchlistItem(watchlist_id=watchlist.id, asset_id=aapl.id),
            WatchlistItem(watchlist_id=watchlist.id, asset_id=samsung.id),
            Position(
                portfolio_id=portfolio.id,
                asset_id=aapl.id,
                quantity=Decimal("1"),
                avg_buy_price=Decimal("100"),
            ),
        ]
    )
    db.commit()

    assert NewsUniverseResolver(db).resolve() == [
        ("005930", "KOSPI", "Samsung Electronics"),
        ("AAPL", "NASDAQ", "Apple Inc."),
    ]


def test_news_universe_resolver_explicit_symbols_skip_missing(db: Session) -> None:
    seed_assets(db)

    assert NewsUniverseResolver(db).resolve(["aapl", "MSFT"]) == [
        ("AAPL", "NASDAQ", "Apple Inc.")
    ]


def test_news_universe_resolver_empty_noop(db: Session) -> None:
    assert NewsUniverseResolver(db).resolve() == []
    result = NewsIngestionService(db).collect_and_save(MixedNewsAdapter({}), [])
    assert result.target_count == 0


class MixedNewsAdapter(NewsAdapter):
    def __init__(
        self,
        results_by_query: dict[str, list[NewsAdapterResult]],
        failing_queries: set[str] | None = None,
    ) -> None:
        self.results_by_query = results_by_query
        self.failing_queries = failing_queries or set()

    def fetch(self, symbols: list[str]) -> list[NewsAdapterResult]:
        return []

    def fetch_query(self, query: str, market: str) -> list[NewsAdapterResult]:
        if query in self.failing_queries:
            raise RuntimeError("target failed")
        return self.results_by_query.get(query, [])


def seed_assets(db: Session) -> tuple[Asset, Asset]:
    aapl = Asset(symbol="aapl", name="Apple Inc.", market="nasdaq")
    samsung = Asset(symbol="005930", name="Samsung Electronics", market="KOSPI")
    db.add_all([aapl, samsung])
    db.commit()
    db.refresh(aapl)
    db.refresh(samsung)
    return aapl, samsung


def news_result(
    title: str,
    url: str,
    published_at: datetime | None = datetime(2026, 6, 18, tzinfo=timezone.utc),
) -> NewsAdapterResult:
    return NewsAdapterResult(
        title=title,
        url=url,
        body="body",
        source="fixture",
        published_at=published_at,
        payload={"url": url},
    )
