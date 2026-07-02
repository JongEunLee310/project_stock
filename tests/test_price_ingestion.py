from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, cast

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.market.base import PriceBarResult, PriceSeriesProvider
from app.adapters.market.yfinance import YFinancePriceProvider, to_yfinance_ticker
from app.domains.assets.model import Asset
from app.domains.ingestion.schema import ProcessingStatus
from app.domains.jobs.model import JobRun
from app.domains.portfolios.model import Portfolio, Position
from app.domains.prices.ingestion_service import PriceIngestionService
from app.domains.prices.model import StockPriceBar
from app.domains.prices.universe import PriceUniverseResolver
from app.domains.raw_prices.model import RawPrice
from app.domains.raw_prices.service import RawPriceService
from app.domains.watchlists.model import Watchlist, WatchlistItem
from app.worker.jobs import prices
from app.worker.jobs.prices import collect_prices_job


def test_yfinance_ticker_mapping() -> None:
    assert to_yfinance_ticker("005930", "KOSPI") == "005930.KS"
    assert to_yfinance_ticker("035720", "KOSDAQ") == "035720.KQ"
    assert to_yfinance_ticker("AAPL", "NASDAQ") == "AAPL"
    assert to_yfinance_ticker("VOD", "LSE") is None


def test_yfinance_provider_parses_history_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeFrame:
        empty = False

        def iterrows(self) -> list[tuple[datetime, dict[str, object]]]:
            return [
                (
                    datetime(2026, 6, 25, tzinfo=UTC),
                    {
                        "Open": 100.1,
                        "High": 110.2,
                        "Low": 90.3,
                        "Close": 105.4,
                        "Adj Close": 104.9,
                        "Volume": 123456,
                    },
                )
            ]

    class FakeTicker:
        fast_info = {"currency": "USD"}

        def __init__(self, ticker: str) -> None:
            self.ticker = ticker

        def history(
            self,
            period: str,
            interval: str,
            auto_adjust: bool,
        ) -> FakeFrame:
            assert self.ticker == "AAPL"
            assert period == "1mo"
            assert interval == "1d"
            assert auto_adjust is True
            return FakeFrame()

    monkeypatch.setattr("app.adapters.market.yfinance.yf.Ticker", FakeTicker)

    bars = YFinancePriceProvider().get_daily_bars(
        "aapl",
        "nasdaq",
        "1M",
        adjusted=True,
    )

    assert bars == [
        PriceBarResult(
            symbol="AAPL",
            market="NASDAQ",
            interval="1d",
            timestamp=datetime(2026, 6, 25, tzinfo=UTC),
            open_price=Decimal("100.1"),
            high_price=Decimal("110.2"),
            low_price=Decimal("90.3"),
            close_price=Decimal("105.4"),
            adjusted_close_price=Decimal("104.9"),
            volume=123456,
            currency="USD",
            source="yfinance",
        )
    ]


def test_yfinance_provider_skips_unknown_market() -> None:
    assert YFinancePriceProvider().get_daily_bars("VOD", "LSE", "1M", True) == []


def test_price_ingestion_validates_and_saves_counts(db: Session) -> None:
    today = date.today()
    provider = StaticPriceProvider(
        [
            price_bar(date=today - timedelta(days=3), close=Decimal("100")),
            price_bar(
                date=today - timedelta(days=2),
                close=cast(Any, None),
            ),
            price_bar(date=today + timedelta(days=1), close=Decimal("101")),
            price_bar(
                date=today - timedelta(days=1),
                close=Decimal("200"),
                currency="EUR",
            ),
        ],
        payload={"fixture": "validation"},
    )

    result = PriceIngestionService(db).collect_and_save(
        provider,
        [("AAPL", "NASDAQ")],
    )

    assert result.target_count == 1
    assert result.success_count == 1
    assert result.failure_count == 0
    assert result.raw_saved_count == 1
    assert result.received_bar_count == 4
    assert result.saved_bar_count == 2
    assert result.dropped_bar_count == 2
    assert result.warning_count == 2
    assert db.scalar(select(func.count()).select_from(StockPriceBar)) == 2


def test_price_ingestion_upsert_is_idempotent(db: Session) -> None:
    bar = price_bar(date=date.today(), close=Decimal("100"))
    service = PriceIngestionService(db)

    service.collect_and_save(StaticPriceProvider([bar], {"run": 1}), [("AAPL", "NASDAQ")])
    service.collect_and_save(StaticPriceProvider([bar], {"run": 2}), [("AAPL", "NASDAQ")])

    assert db.scalar(select(func.count()).select_from(StockPriceBar)) == 1


def test_raw_price_service_skips_duplicate_payload(db: Session) -> None:
    service = RawPriceService(db)
    payload = {"ticker": "AAPL", "rows": [{"close": "100"}]}

    first = service.save_raw("AAPL", "NASDAQ", payload)
    second = service.save_raw("AAPL", "NASDAQ", payload)

    assert first is not None
    assert second is None
    assert db.scalar(select(func.count()).select_from(RawPrice)) == 1


def test_raw_price_service_defaults_processing_status_to_fetched(
    db: Session,
) -> None:
    raw_price = RawPriceService(db).save_raw(
        "AAPL",
        "NASDAQ",
        {"ticker": "AAPL", "rows": [{"close": "100"}]},
    )

    assert raw_price is not None
    assert raw_price.processing_status == ProcessingStatus.FETCHED.value


def test_raw_price_processing_status_accepts_pipeline_states(db: Session) -> None:
    raw_price = RawPrice(
        symbol="AAPL",
        market="NASDAQ",
        interval="1d",
        source="fixture",
        payload={"ticker": "AAPL"},
        payload_hash="raw-price-normalized",
        processing_status=ProcessingStatus.NORMALIZED.value,
    )
    failed_raw_price = RawPrice(
        symbol="MSFT",
        market="NASDAQ",
        interval="1d",
        source="fixture",
        payload={"ticker": "MSFT"},
        payload_hash="raw-price-failed",
        processing_status=ProcessingStatus.FAILED.value,
    )
    db.add_all([raw_price, failed_raw_price])
    db.commit()

    statuses = set(db.scalars(select(RawPrice.processing_status)).all())

    assert ProcessingStatus.NORMALIZED.value in statuses
    assert ProcessingStatus.FAILED.value in statuses


def test_price_universe_resolver_deduplicates_watchlist_and_portfolio(
    db: Session,
) -> None:
    aapl = Asset(symbol="aapl", name="Apple Inc.", market="nasdaq")
    samsung = Asset(symbol="005930", name="Samsung", market="KOSPI")
    db.add_all([aapl, samsung])
    db.commit()
    db.refresh(aapl)
    db.refresh(samsung)
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

    assert PriceUniverseResolver(db).resolve() == [
        ("005930", "KOSPI"),
        ("AAPL", "NASDAQ"),
    ]


def test_price_universe_resolver_empty_noop(db: Session) -> None:
    assert PriceUniverseResolver(db).resolve() == []


def test_collect_prices_job_records_success_with_target_failure(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(prices, "SessionLocal", lambda: db)
    monkeypatch.setattr(prices, "get_price_series_provider", lambda: MixedProvider())
    aapl = Asset(symbol="AAPL", name="Apple Inc.", market="NASDAQ")
    fail = Asset(symbol="FAIL", name="Failure Corp.", market="NASDAQ")
    db.add_all([aapl, fail])
    db.commit()
    db.refresh(aapl)
    db.refresh(fail)
    watchlist = Watchlist(user_id=1, name="Main")
    db.add(watchlist)
    db.commit()
    db.refresh(watchlist)
    db.add_all(
        [
            WatchlistItem(watchlist_id=watchlist.id, asset_id=aapl.id),
            WatchlistItem(watchlist_id=watchlist.id, asset_id=fail.id),
        ]
    )
    db.commit()

    collect_prices_job()

    job_run = db.scalars(select(JobRun)).one()
    assert job_run.job_type == "price_collection"
    assert job_run.status == "success"
    assert job_run.finished_at is not None
    assert db.scalar(select(func.count()).select_from(StockPriceBar)) == 1


class StaticPriceProvider(PriceSeriesProvider):
    source = "fixture"

    def __init__(
        self,
        bars: list[PriceBarResult],
        payload: dict[str, object],
    ) -> None:
        self.bars = bars
        self.last_payload = payload

    def get_daily_bars(
        self,
        symbol: str,
        market: str,
        range_value: str,
        adjusted: bool,
    ) -> list[PriceBarResult]:
        return self.bars


class MixedProvider(PriceSeriesProvider):
    source = "fixture"

    def get_daily_bars(
        self,
        symbol: str,
        market: str,
        range_value: str,
        adjusted: bool,
    ) -> list[PriceBarResult]:
        if symbol == "FAIL":
            raise RuntimeError("target failed")
        self.last_payload = {"symbol": symbol, "market": market}
        return [price_bar(date=date.today(), close=Decimal("100"), symbol=symbol)]


def price_bar(
    date: date,
    close: Decimal,
    symbol: str = "AAPL",
    currency: str = "USD",
) -> PriceBarResult:
    return PriceBarResult(
        symbol=symbol,
        market="NASDAQ",
        interval="1d",
        timestamp=datetime.combine(date, time.min, tzinfo=UTC),
        open_price=Decimal("100"),
        high_price=Decimal("110"),
        low_price=Decimal("90"),
        close_price=close,
        adjusted_close_price=close,
        volume=1000,
        currency=currency,
        source="fixture",
    )
