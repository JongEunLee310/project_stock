from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest

from app.adapters.disclosure.mock import MockDisclosureProvider
from app.adapters.factory import (
    get_disclosure_provider,
    get_exchange_rate_provider,
    get_earnings_provider,
    get_index_quote_provider,
    get_market_provider,
    get_news_adapter,
    get_portfolio_provider,
    get_price_series_provider,
    get_symbol_lookup_provider,
    get_valuation_provider,
)
from app.adapters.market.mock import (
    MockEarningsProvider,
    MockExchangeRateProvider,
    MockIndexQuoteProvider,
    MockMarketDataProvider,
    MockPriceSeriesProvider,
    MockSymbolLookupProvider,
    MockValuationProvider,
)
from app.adapters.market.yfinance import (
    YFinanceEarningsProvider,
    YFinanceExchangeRateProvider,
    YFinanceIndexQuoteProvider,
    YFinanceMarketDataProvider,
    YFinancePriceProvider,
    YFinanceSymbolLookupProvider,
    YFinanceValuationProvider,
    quote_result_from_fast_info,
    to_yfinance_quote_ticker,
)
from app.adapters.market.cache import (
    CachedExchangeRateProvider,
    CachedIndexQuoteProvider,
    CachedMarketDataProvider,
)
from app.adapters.news.mock import MockNewsAdapter
from app.adapters.news.rss import RSSNewsAdapter
from app.adapters.portfolio.mock import MockPortfolioProvider
from app.core.config import settings


def test_mock_market_data_provider_returns_deterministic_quotes() -> None:
    provider = MockMarketDataProvider()

    first_result = provider.get_quote(["AAPL", "MSFT"])
    second_result = provider.get_quote(["AAPL", "MSFT"])

    assert first_result == second_result
    assert [quote.symbol for quote in first_result] == ["AAPL", "MSFT"]
    assert first_result[0].name == "Apple Inc."


def test_quote_result_from_fast_info_derives_required_values() -> None:
    as_of = datetime(2026, 7, 13, 1, 2, tzinfo=UTC)

    result = quote_result_from_fast_info(
        "aapl",
        {
            # Fixture values are synthetic yfinance fast_info-shaped data.
            "last_price": 195.64,
            "previous_close": 193.20,
            "currency": "usd",
            "market_cap": 3_000_000_000_000,
            "year_low": 164.08,
            "year_high": 237.49,
        },
        as_of=as_of,
    )

    assert result is not None
    assert result.symbol == "AAPL"
    assert result.name == "AAPL"
    assert result.price == Decimal("195.64")
    assert result.previous_close == Decimal("193.2")
    assert result.change == Decimal("2.44")
    assert result.change_percent == Decimal("1.26")
    assert result.currency == "USD"
    assert result.market_cap == Decimal("3000000000000")
    assert result.fifty_two_week_low == Decimal("164.08")
    assert result.fifty_two_week_high == Decimal("237.49")
    assert result.per is None
    assert result.target_price is None
    assert result.as_of == as_of


@pytest.mark.parametrize(
    ("previous_close", "expected"),
    [(None, None), (0, Decimal("0.00"))],
)
def test_quote_result_from_fast_info_guards_previous_close(
    previous_close: float | None,
    expected: Decimal | None,
) -> None:
    result = quote_result_from_fast_info(
        "AAPL",
        {"last_price": 10, "previous_close": previous_close, "currency": "usd"},
        as_of=datetime(2026, 7, 13, tzinfo=UTC),
    )

    if expected is None:
        assert result is None
    else:
        assert result is not None
        assert result.change_percent == expected


@pytest.mark.parametrize(
    ("symbol", "expected"),
    [("005930", "005930.KS"), ("AAPL", "AAPL"), ("BRK-B", "BRK-B")],
)
def test_to_yfinance_quote_ticker_uses_numeric_krx_heuristic(
    symbol: str,
    expected: str,
) -> None:
    assert to_yfinance_quote_ticker(symbol) == expected


class StubTicker:
    fast_info_by_symbol: dict[str, Any] = {}

    def __init__(self, symbol: str) -> None:
        self.fast_info = self.fast_info_by_symbol[symbol]


def test_yfinance_market_provider_skips_individual_symbol_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    StubTicker.fast_info_by_symbol = {
        "AAPL": {
            "last_price": 195.64,
            "previous_close": 193.20,
            "currency": "usd",
        }
    }
    monkeypatch.setattr("app.adapters.market.yfinance.yf.Ticker", StubTicker)

    results = YFinanceMarketDataProvider().get_quote(["AAPL", "MISSING"])

    assert [result.symbol for result in results] == ["AAPL"]


def test_yfinance_index_provider_maps_symbols_and_preserves_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    StubTicker.fast_info_by_symbol = {
        "^GSPC": {"last_price": 5600, "previous_close": 5572},
        "^IXIC": {"last_price": 18000, "previous_close": 18000},
        "^KS11": {"last_price": 3200, "previous_close": 3200},
        "^VIX": {"last_price": 15, "previous_close": 15},
    }
    monkeypatch.setattr("app.adapters.market.yfinance.yf.Ticker", StubTicker)

    results = YFinanceIndexQuoteProvider().get_quotes(
        ["SPX", "UNKNOWN", "IXIC", "KOSPI", "VIX"]
    )

    assert [(result.symbol, result.name) for result in results] == [
        ("SPX", "S&P 500"),
        ("IXIC", "NASDAQ Composite"),
        ("KOSPI", "KOSPI"),
        ("VIX", "VIX"),
    ]
    # Synthetic fixture: (5600 - 5572) / 5572 * 100.
    assert results[0].change_percent == Decimal("0.50")


def test_yfinance_exchange_rate_provider_maps_pair_and_guards_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    StubTicker.fast_info_by_symbol = {
        # Fixture values are synthetic yfinance fast_info-shaped data.
        "KRW=X": {"last_price": 1384.5, "previous_close": 0},
    }
    monkeypatch.setattr("app.adapters.market.yfinance.yf.Ticker", StubTicker)

    results = YFinanceExchangeRateProvider().get_rates(["USD/KRW", "EUR/KRW"])

    assert [result.pair for result in results] == ["USD/KRW"]
    assert results[0].rate == Decimal("1384.5")
    assert results[0].change_percent == Decimal("0.00")


def test_mock_price_series_provider_returns_deterministic_bars() -> None:
    provider = MockPriceSeriesProvider()

    first_result = provider.get_daily_bars("AAPL", "NASDAQ", "1M", adjusted=True)
    second_result = provider.get_daily_bars("AAPL", "NASDAQ", "1M", adjusted=True)

    assert first_result == second_result
    assert len(first_result) == 22
    assert first_result[0].symbol == "AAPL"
    assert first_result[0].market == "NASDAQ"
    assert first_result[0].timestamp.tzinfo is not None


def test_mock_price_series_provider_supports_five_year_range() -> None:
    bars = MockPriceSeriesProvider().get_daily_bars(
        "AAPL", "NASDAQ", "5Y", adjusted=True
    )

    assert len(bars) == 1260


def test_mock_earnings_provider_returns_deterministic_event_history() -> None:
    provider = MockEarningsProvider()

    first_result = provider.get_earnings_events("AAPL", "NASDAQ")
    second_result = provider.get_earnings_events("AAPL", "NASDAQ")

    assert first_result == second_result
    assert len(first_result) == 9
    assert sum(result.eps_actual is None for result in first_result) == 1
    assert sum(result.eps_estimate is None for result in first_result) == 1
    assert sum(result.event_date > date.today() for result in first_result) == 1


def test_mock_symbol_lookup_provider_matches_symbol_partially() -> None:
    provider = MockSymbolLookupProvider()

    results = provider.search("AAP")

    assert [result.symbol for result in results] == ["AAPL"]


def test_mock_symbol_lookup_provider_matches_name_case_insensitively() -> None:
    provider = MockSymbolLookupProvider()

    results = provider.search("microsoft")

    assert [(result.symbol, result.name) for result in results] == [
        ("MSFT", "Microsoft Corporation")
    ]


def test_mock_symbol_lookup_provider_filters_by_market() -> None:
    provider = MockSymbolLookupProvider()

    assert [result.symbol for result in provider.search("Visa")] == ["V"]
    assert provider.search("Visa", market="NASDAQ") == []


def test_mock_symbol_lookup_provider_returns_empty_list_for_no_results() -> None:
    assert MockSymbolLookupProvider().search("not-a-symbol") == []


def test_mock_disclosure_provider_returns_deterministic_disclosures() -> None:
    provider = MockDisclosureProvider()

    first_result = provider.fetch(["aapl"])
    second_result = provider.fetch(["aapl"])

    assert first_result == second_result
    assert first_result[0].symbol == "AAPL"
    assert first_result[0].payload == {"symbol": "AAPL", "index": 1}


def test_mock_portfolio_provider_returns_deterministic_holdings() -> None:
    provider = MockPortfolioProvider()

    first_result = provider.fetch_holdings("demo-account")
    second_result = provider.fetch_holdings("demo-account")

    assert first_result == second_result
    assert [holding.symbol for holding in first_result] == ["AAPL", "TSLA"]
    assert {holding.account_ref for holding in first_result} == {"demo-account"}


def test_factories_return_mock_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "MARKET_PROVIDER", "mock")
    monkeypatch.setattr(settings, "NEWS_PROVIDER", "mock")
    monkeypatch.setattr(settings, "DISCLOSURE_PROVIDER", "mock")
    monkeypatch.setattr(settings, "PORTFOLIO_PROVIDER", "mock")

    assert isinstance(get_market_provider(), MockMarketDataProvider)
    assert isinstance(get_price_series_provider(), MockPriceSeriesProvider)
    assert isinstance(get_index_quote_provider(), MockIndexQuoteProvider)
    assert isinstance(get_exchange_rate_provider(), MockExchangeRateProvider)
    assert isinstance(get_symbol_lookup_provider(), MockSymbolLookupProvider)
    assert isinstance(get_valuation_provider(), MockValuationProvider)
    assert isinstance(get_earnings_provider(), MockEarningsProvider)
    assert isinstance(get_news_adapter(), MockNewsAdapter)
    assert isinstance(get_disclosure_provider(), MockDisclosureProvider)
    assert isinstance(get_portfolio_provider(), MockPortfolioProvider)


def test_price_series_factory_returns_yfinance_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "MARKET_PROVIDER", "yfinance")

    assert isinstance(get_price_series_provider(), YFinancePriceProvider)


def test_symbol_lookup_factory_returns_yfinance_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "MARKET_PROVIDER", "yfinance")

    assert isinstance(get_symbol_lookup_provider(), YFinanceSymbolLookupProvider)


def test_valuation_factory_returns_yfinance_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "MARKET_PROVIDER", "yfinance")

    assert isinstance(get_valuation_provider(), YFinanceValuationProvider)


def test_earnings_factory_returns_yfinance_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "MARKET_PROVIDER", "yfinance")

    assert isinstance(get_earnings_provider(), YFinanceEarningsProvider)


def test_quote_index_and_fx_factories_wrap_yfinance_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "MARKET_PROVIDER", "yfinance")

    assert isinstance(get_market_provider(), CachedMarketDataProvider)
    assert isinstance(get_index_quote_provider(), CachedIndexQuoteProvider)
    assert isinstance(get_exchange_rate_provider(), CachedExchangeRateProvider)


def test_news_factory_returns_rss_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "NEWS_PROVIDER", "rss")
    monkeypatch.setattr(
        settings,
        "NEWS_QUERY_URL_TEMPLATE",
        "https://example.com/rss?q={query}&hl={hl}&gl={gl}",
    )

    adapter = get_news_adapter()

    assert isinstance(adapter, RSSNewsAdapter)
    assert adapter.query_url_template == "https://example.com/rss?q={query}&hl={hl}&gl={gl}"


@pytest.mark.parametrize(
    ("setting_name", "factory_name"),
    [
        ("MARKET_PROVIDER", "get_market_provider"),
        ("MARKET_PROVIDER", "get_price_series_provider"),
        ("MARKET_PROVIDER", "get_index_quote_provider"),
        ("MARKET_PROVIDER", "get_exchange_rate_provider"),
        ("MARKET_PROVIDER", "get_symbol_lookup_provider"),
        ("MARKET_PROVIDER", "get_valuation_provider"),
        ("MARKET_PROVIDER", "get_earnings_provider"),
        ("NEWS_PROVIDER", "get_news_adapter"),
        ("DISCLOSURE_PROVIDER", "get_disclosure_provider"),
        ("PORTFOLIO_PROVIDER", "get_portfolio_provider"),
    ],
)
def test_factories_fail_fast_for_real_providers(
    monkeypatch: pytest.MonkeyPatch,
    setting_name: str,
    factory_name: str,
) -> None:
    factories = {
        "get_market_provider": get_market_provider,
        "get_price_series_provider": get_price_series_provider,
        "get_index_quote_provider": get_index_quote_provider,
        "get_exchange_rate_provider": get_exchange_rate_provider,
        "get_symbol_lookup_provider": get_symbol_lookup_provider,
        "get_valuation_provider": get_valuation_provider,
        "get_earnings_provider": get_earnings_provider,
        "get_news_adapter": get_news_adapter,
        "get_disclosure_provider": get_disclosure_provider,
        "get_portfolio_provider": get_portfolio_provider,
    }
    monkeypatch.setattr(settings, setting_name, "real")

    with pytest.raises(NotImplementedError, match="real provider 미구현"):
        factories[factory_name]()
