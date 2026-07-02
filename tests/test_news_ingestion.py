from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.news.base import NewsAdapter, NewsAdapterResult
from app.domains.assets.model import Asset
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


def news_result(title: str, url: str) -> NewsAdapterResult:
    return NewsAdapterResult(
        title=title,
        url=url,
        body="body",
        source="fixture",
        published_at=datetime(2026, 6, 18, tzinfo=timezone.utc),
        payload={"url": url},
    )
