from app.adapters.disclosure.base import DisclosureProvider
from app.adapters.disclosure.mock import MockDisclosureProvider
from app.adapters.llm.base import LLMClient
from app.adapters.llm.gateway import CLOUD, LOCAL, LLMGateway
from app.adapters.llm.local import LocalLLMProvider
from app.adapters.llm.mock import DEFAULT_MOCK_RESPONSES, MockLLMClient
from app.adapters.llm.openai import OpenAIClient
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


def get_llm_client(provider: str | None = None) -> LLMClient:
    selected_provider = settings.LLM_PROVIDER if provider is None else provider
    if selected_provider == "cloud":
        api_key = settings.OPENAI_API_KEY
        if api_key is None or not api_key.strip():
            raise RuntimeError("OPENAI_API_KEY is required when LLM_PROVIDER=cloud")
        return OpenAIClient(api_key=api_key)
    if selected_provider == "local":
        return LocalLLMProvider()
    if selected_provider == "mock":
        return MockLLMClient(DEFAULT_MOCK_RESPONSES)
    raise NotImplementedError(f"llm provider 미구현: {selected_provider}")


def get_llm_gateway() -> LLMGateway:
    if settings.LLM_PROVIDER == "mock":
        mock_client = get_llm_client("mock")
        return LLMGateway({CLOUD: mock_client, LOCAL: mock_client})
    if settings.LLM_PROVIDER == "cloud":
        return LLMGateway(
            {
                CLOUD: get_llm_client("cloud"),
                LOCAL: get_llm_client("local"),
            }
        )
    if settings.LLM_PROVIDER == "local":
        local_client = get_llm_client("local")
        return LLMGateway({LOCAL: local_client, CLOUD: local_client})
    raise NotImplementedError(f"llm provider 미구현: {settings.LLM_PROVIDER}")
