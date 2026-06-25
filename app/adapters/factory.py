from app.adapters.disclosure.base import DisclosureProvider
from app.adapters.disclosure.mock import MockDisclosureProvider
from app.adapters.market.base import MarketDataProvider, PriceSeriesProvider
from app.adapters.market.mock import MockMarketDataProvider, MockPriceSeriesProvider
from app.adapters.news.base import NewsAdapter
from app.adapters.news.mock import MockNewsAdapter
from app.adapters.portfolio.base import PortfolioProvider
from app.adapters.portfolio.mock import MockPortfolioProvider
from app.core.config import settings


def get_market_provider() -> MarketDataProvider:
    if settings.MARKET_PROVIDER == "mock":
        return MockMarketDataProvider()
    raise NotImplementedError("market real provider 미구현")


def get_price_series_provider() -> PriceSeriesProvider:
    if settings.MARKET_PROVIDER == "mock":
        return MockPriceSeriesProvider()
    raise NotImplementedError("market real provider 미구현")


def get_news_adapter() -> NewsAdapter:
    if settings.NEWS_PROVIDER == "mock":
        return MockNewsAdapter()
    raise NotImplementedError("news real provider 미구현")


def get_disclosure_provider() -> DisclosureProvider:
    if settings.DISCLOSURE_PROVIDER == "mock":
        return MockDisclosureProvider()
    raise NotImplementedError("disclosure real provider 미구현")


def get_portfolio_provider() -> PortfolioProvider:
    if settings.PORTFOLIO_PROVIDER == "mock":
        return MockPortfolioProvider()
    raise NotImplementedError("portfolio real provider 미구현")
