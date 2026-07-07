from app.adapters.disclosure.base import DisclosureProvider
from app.adapters.disclosure.mock import MockDisclosureProvider
from app.adapters.llm.base import LLMClient
from app.adapters.llm.budget import DailyCallBudget
from app.adapters.llm.cache import LLMResponseCache
from app.adapters.llm.escalation import EscalationPolicy
from app.adapters.llm.gateway import CLOUD, LOCAL, LLMGateway
from app.adapters.llm.local import LocalLLMProvider
from app.adapters.llm.mock import DEFAULT_MOCK_RESPONSES, MockLLMClient
from app.adapters.llm.openai import OpenAIClient
from app.adapters.market.base import (
    ExchangeRateProvider,
    IndexQuoteProvider,
    MarketDataProvider,
    PriceSeriesProvider,
    SymbolLookupProvider,
)
from app.adapters.market.mock import (
    MockExchangeRateProvider,
    MockIndexQuoteProvider,
    MockMarketDataProvider,
    MockPriceSeriesProvider,
    MockSymbolLookupProvider,
)
from app.adapters.market.yfinance import YFinancePriceProvider, YFinanceSymbolLookupProvider
from app.adapters.news.base import NewsAdapter
from app.adapters.news.mock import MockNewsAdapter
from app.adapters.news.rss import RSSNewsAdapter
from app.adapters.portfolio.base import PortfolioProvider
from app.adapters.portfolio.mock import MockPortfolioProvider
from app.core.config import settings
from app.worker.connection import get_redis_connection

LOCAL_PROXY_OPENAI_API_KEY = "local-proxy"


def get_market_provider() -> MarketDataProvider:
    if settings.MARKET_PROVIDER == "mock":
        return MockMarketDataProvider()
    raise NotImplementedError("market real provider 미구현")


def get_price_series_provider() -> PriceSeriesProvider:
    if settings.MARKET_PROVIDER == "mock":
        return MockPriceSeriesProvider()
    if settings.MARKET_PROVIDER == "yfinance":
        return YFinancePriceProvider()
    raise NotImplementedError("market real provider 미구현")


def get_index_quote_provider() -> IndexQuoteProvider:
    if settings.MARKET_PROVIDER == "mock":
        return MockIndexQuoteProvider()
    raise NotImplementedError("market real provider 미구현")


def get_exchange_rate_provider() -> ExchangeRateProvider:
    if settings.MARKET_PROVIDER == "mock":
        return MockExchangeRateProvider()
    raise NotImplementedError("market real provider 미구현")


def get_symbol_lookup_provider() -> SymbolLookupProvider:
    if settings.MARKET_PROVIDER == "mock":
        return MockSymbolLookupProvider()
    if settings.MARKET_PROVIDER == "yfinance":
        return YFinanceSymbolLookupProvider()
    raise NotImplementedError("market real provider 미구현")


def get_news_adapter() -> NewsAdapter:
    if settings.NEWS_PROVIDER == "mock":
        return MockNewsAdapter()
    if settings.NEWS_PROVIDER == "rss":
        return RSSNewsAdapter([], query_url_template=settings.NEWS_QUERY_URL_TEMPLATE)
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
        base_url = settings.OPENAI_BASE_URL
        api_key = settings.OPENAI_API_KEY
        if api_key is None or not api_key.strip():
            if base_url is None:
                raise RuntimeError("OPENAI_API_KEY is required when LLM_PROVIDER=cloud")
            api_key = LOCAL_PROXY_OPENAI_API_KEY
        return OpenAIClient(
            api_key=api_key,
            model=settings.OPENAI_MODEL,
            base_url=base_url,
        )
    if selected_provider == "local":
        return LocalLLMProvider()
    if selected_provider == "mock":
        return MockLLMClient(DEFAULT_MOCK_RESPONSES)
    raise NotImplementedError(f"llm provider 미구현: {selected_provider}")


def get_llm_gateway() -> LLMGateway:
    if settings.LLM_PROVIDER == "mock":
        mock_client = get_llm_client("mock")
        return LLMGateway(
            {CLOUD: mock_client, LOCAL: mock_client},
            timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
        )
    if settings.LLM_PROVIDER == "cloud":
        redis = (
            get_redis_connection()
            if settings.LLM_DAILY_CALL_LIMIT is not None
            or settings.LLM_CACHE_TTL_SECONDS is not None
            else None
        )
        call_budget = (
            DailyCallBudget(redis, settings.LLM_DAILY_CALL_LIMIT)
            if redis is not None and settings.LLM_DAILY_CALL_LIMIT is not None
            else None
        )
        response_cache = (
            LLMResponseCache(redis, settings.LLM_CACHE_TTL_SECONDS)
            if redis is not None and settings.LLM_CACHE_TTL_SECONDS is not None
            else None
        )
        escalation_policy = (
            EscalationPolicy(settings.LLM_ESCALATION_CONFIDENCE_THRESHOLD)
            if settings.LLM_ESCALATION_ENABLED
            else None
        )
        return LLMGateway(
            {
                CLOUD: get_llm_client("cloud"),
                LOCAL: get_llm_client("local"),
            },
            timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
            call_budget=call_budget,
            response_cache=response_cache,
            escalation_policy=escalation_policy,
        )
    if settings.LLM_PROVIDER == "local":
        local_client = get_llm_client("local")
        return LLMGateway(
            {LOCAL: local_client, CLOUD: local_client},
            timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
        )
    raise NotImplementedError(f"llm provider 미구현: {settings.LLM_PROVIDER}")
