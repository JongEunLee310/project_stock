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
    analyst_opinions_from_frame,
    price_target_result_from_info,
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


def test_mock_market_data_provider_price_target_invariant() -> None:
    result = MockMarketDataProvider().get_price_targets(["AAPL"])[0]

    assert result.target_price_high is not None
    assert result.target_price is not None
    assert result.target_price_low is not None
    assert result.target_price_high >= result.target_price >= result.target_price_low
    assert result.target_analyst_count is not None


def test_mock_market_data_provider_returns_deterministic_analyst_opinions() -> None:
    provider = MockMarketDataProvider()

    first_result = provider.get_analyst_opinions("AAPL", 2)
    second_result = provider.get_analyst_opinions("aapl", 2)

    assert first_result == second_result
    assert len(first_result) == 2
    assert first_result[0].firm == "JPMorgan"
    assert first_result[0].price_target == Decimal("250.00")
    assert provider.get_analyst_opinions("005930", 20) == []


def test_analyst_opinions_from_frame_normalizes_and_sorts() -> None:
    class Frame:
        empty = False

        def iterrows(self) -> list[tuple[datetime, dict[str, Any]]]:
            return [
                (
                    datetime(2026, 7, 13, tzinfo=UTC),
                    {
                        "Firm": "Older Firm",
                        "Action": "UP",
                        "ToGrade": "Buy",
                        "FromGrade": "",
                        "currentPriceTarget": 0.0,
                        "priorPriceTarget": float("nan"),
                        "priceTargetAction": None,
                    },
                ),
                (
                    datetime(2026, 7, 15),
                    {
                        "Firm": "Newer Firm",
                        "Action": "MAIN",
                        "ToGrade": float("nan"),
                        "FromGrade": "Hold",
                        "currentPriceTarget": 245.5,
                        "priorPriceTarget": 230,
                        "priceTargetAction": "Raises",
                    },
                ),
            ]

    results = analyst_opinions_from_frame(Frame(), limit=1)

    assert len(results) == 1
    assert results[0].firm == "Newer Firm"
    assert results[0].action == "main"
    assert results[0].to_grade is None
    assert results[0].from_grade == "Hold"
    assert results[0].price_target == Decimal("245.5")
    assert results[0].prior_price_target == Decimal("230")
    assert results[0].price_target_action == "Raises"
    assert results[0].published_at == datetime(2026, 7, 15, tzinfo=UTC)


def test_analyst_opinions_from_frame_normalizes_zero_and_empty_grade() -> None:
    class Frame:
        empty = False

        def iterrows(self) -> list[tuple[datetime, dict[str, Any]]]:
            return [
                (
                    datetime(2026, 7, 13, tzinfo=UTC),
                    {
                        "Firm": "Firm",
                        "Action": "INIT",
                        "ToGrade": "Buy",
                        "FromGrade": "  ",
                        "currentPriceTarget": 0,
                        "priorPriceTarget": 0.0,
                        "priceTargetAction": "",
                    },
                )
            ]

    result = analyst_opinions_from_frame(Frame(), limit=20)[0]

    assert result.from_grade is None
    assert result.price_target is None
    assert result.prior_price_target is None
    assert result.price_target_action is None


def test_quote_result_from_fast_info_derives_required_values() -> None:
    as_of = datetime(2026, 7, 13, 1, 2, tzinfo=UTC)

    result = quote_result_from_fast_info(
        "aapl",
        {
            # FastInfo exposes camelCase keys through its mapping interface.
            "lastPrice": 195.64,
            "previousClose": 193.20,
            "currency": "usd",
            "marketCap": 3_000_000_000_000,
            "yearLow": 164.08,
            "yearHigh": 237.49,
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


def test_price_target_result_from_info_converts_consensus_values() -> None:
    result = price_target_result_from_info(
        "aapl",
        {
            "targetMeanPrice": 220.5,
            "targetHighPrice": 250,
            "targetLowPrice": 180,
            "numberOfAnalystOpinions": 42,
        },
    )

    assert result.symbol == "AAPL"
    assert result.target_price == Decimal("220.5")
    assert result.target_price_high == Decimal("250")
    assert result.target_price_low == Decimal("180")
    assert result.target_analyst_count == 42


def test_price_target_result_from_info_allows_missing_consensus() -> None:
    result = price_target_result_from_info("005930", {})

    assert result.symbol == "005930"
    assert result.target_price is None
    assert result.target_price_high is None
    assert result.target_price_low is None
    assert result.target_analyst_count is None


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
        {"lastPrice": 10, "previousClose": previous_close, "currency": "usd"},
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


class StubFastInfo(dict[str, Any]):
    _DICT_KEYS = {
        "last_price": "lastPrice",
        "previous_close": "previousClose",
        "currency": "currency",
        "market_cap": "marketCap",
        "year_low": "yearLow",
        "year_high": "yearHigh",
    }

    def __init__(self, **attributes: Any) -> None:
        super().__init__(
            (self._DICT_KEYS[key], value) for key, value in attributes.items()
        )
        for key, value in attributes.items():
            setattr(self, key, value)


class StubTicker:
    fast_info_by_symbol: dict[str, Any] = {}
    info_by_symbol: dict[str, Any] = {}
    upgrades_downgrades_by_symbol: dict[str, Any] = {}

    def __init__(self, symbol: str) -> None:
        self.fast_info = self.fast_info_by_symbol.get(symbol)
        self.info = self.info_by_symbol.get(symbol, {})
        self.upgrades_downgrades = self.upgrades_downgrades_by_symbol.get(symbol)


def test_yfinance_market_provider_skips_individual_symbol_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    StubTicker.fast_info_by_symbol = {
        "AAPL": StubFastInfo(
            last_price=195.64,
            previous_close=193.20,
            currency="usd",
        )
    }
    assert StubTicker.fast_info_by_symbol["AAPL"].get("last_price") is None
    monkeypatch.setattr("app.adapters.market.yfinance.yf.Ticker", StubTicker)

    results = YFinanceMarketDataProvider().get_quote(["AAPL", "MISSING"])

    assert [result.symbol for result in results] == ["AAPL"]


def test_yfinance_market_provider_collects_price_target_info(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    StubTicker.fast_info_by_symbol = {}
    StubTicker.info_by_symbol = {
        "AAPL": {
            "targetMeanPrice": 220,
            "targetHighPrice": 250,
            "targetLowPrice": 180,
            "numberOfAnalystOpinions": 42,
        },
        "005930.KS": {},
    }
    monkeypatch.setattr("app.adapters.market.yfinance.yf.Ticker", StubTicker)

    results = YFinanceMarketDataProvider().get_price_targets(["AAPL", "005930"])

    assert results[0].target_price == Decimal("220")
    assert results[0].target_analyst_count == 42
    assert results[1].symbol == "005930"
    assert results[1].target_price is None


def test_yfinance_market_provider_collects_analyst_opinions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Frame:
        empty = False

        def iterrows(self) -> list[tuple[datetime, dict[str, Any]]]:
            return [
                (
                    datetime(2026, 7, 15, tzinfo=UTC),
                    {
                        "Firm": "JPMorgan",
                        "Action": "MAIN",
                        "ToGrade": "Overweight",
                        "FromGrade": "Neutral",
                        "currentPriceTarget": 250,
                        "priorPriceTarget": 240,
                        "priceTargetAction": "Raises",
                    },
                )
            ]

    StubTicker.upgrades_downgrades_by_symbol = {"AAPL": Frame()}
    monkeypatch.setattr("app.adapters.market.yfinance.yf.Ticker", StubTicker)

    results = YFinanceMarketDataProvider().get_analyst_opinions("aapl", 20)

    assert len(results) == 1
    assert results[0].firm == "JPMorgan"
    assert results[0].price_target == Decimal("250")


def test_yfinance_index_provider_maps_symbols_and_preserves_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    StubTicker.fast_info_by_symbol = {
        "^GSPC": StubFastInfo(last_price=5600, previous_close=5572),
        "^IXIC": StubFastInfo(last_price=18000, previous_close=18000),
        "^KS11": StubFastInfo(last_price=3200, previous_close=3200),
        "^VIX": StubFastInfo(last_price=15, previous_close=15),
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
        "KRW=X": StubFastInfo(last_price=1384.5, previous_close=0),
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

    assert len(bars) == 260
    assert all(bar.interval == "1wk" for bar in bars)
    assert all(bar.timestamp.weekday() == 0 for bar in bars)


def test_mock_price_series_provider_supports_thirty_minute_range() -> None:
    provider = MockPriceSeriesProvider()

    first_result = provider.get_intraday_bars("AAPL", "NASDAQ", interval="30m")
    second_result = provider.get_intraday_bars("AAPL", "NASDAQ", interval="30m")

    assert first_result == second_result
    assert len(first_result) == 65
    assert all(bar.interval == "30m" for bar in first_result)


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
