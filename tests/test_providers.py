import pytest

from app.adapters.disclosure.mock import MockDisclosureProvider
from app.adapters.factory import (
    get_disclosure_provider,
    get_market_provider,
    get_news_adapter,
    get_portfolio_provider,
)
from app.adapters.market.mock import MockMarketDataProvider
from app.adapters.news.mock import MockNewsAdapter
from app.adapters.portfolio.mock import MockPortfolioProvider
from app.core.config import settings


def test_mock_market_data_provider_returns_deterministic_quotes() -> None:
    provider = MockMarketDataProvider()

    first_result = provider.get_quote(["AAPL", "MSFT"])
    second_result = provider.get_quote(["AAPL", "MSFT"])

    assert first_result == second_result
    assert [quote.symbol for quote in first_result] == ["AAPL", "MSFT"]
    assert first_result[0].name == "Apple Inc."


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
    assert isinstance(get_news_adapter(), MockNewsAdapter)
    assert isinstance(get_disclosure_provider(), MockDisclosureProvider)
    assert isinstance(get_portfolio_provider(), MockPortfolioProvider)


@pytest.mark.parametrize(
    ("setting_name", "factory_name"),
    [
        ("MARKET_PROVIDER", "get_market_provider"),
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
        "get_news_adapter": get_news_adapter,
        "get_disclosure_provider": get_disclosure_provider,
        "get_portfolio_provider": get_portfolio_provider,
    }
    monkeypatch.setattr(settings, setting_name, "real")

    with pytest.raises(NotImplementedError, match="real provider 미구현"):
        factories[factory_name]()
